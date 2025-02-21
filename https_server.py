#!/usr/bin/env python3
import asyncio
import logging
import uuid
from aiohttp import web
from aiohttp.client import ClientResponse
from aiohttp_cors import setup as cors_setup, ResourceOptions, CorsViewMixin

import vyper
from vyper.compiler import compile_code
from vyper.exceptions import VyperException

from concurrent.futures import ThreadPoolExecutor

routes = web.RouteTableDef()
headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Requested-With",
    "Access-Control-Max-Age": "86400",
}
executor_pool = ThreadPoolExecutor(max_workers=4)

# Global dictionary for storing compilation results.
compilation_results = {}

@routes.options('/{tail:.*}')
async def options_handler(request):
    return web.Response(headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Max-Age': '86400',
    })

@routes.get('/')
async def handle(request):
    return web.Response(text='Vyper Compiler. Version: {} \n'.format(vyper.__version__))

def _compile(data):
    # Add debug information about Vyper
    logging.debug(f"Vyper version: {vyper.__version__}")
    from inspect import signature
    logging.debug(f"compile_code signature: {signature(compile_code)}")
    
    # Ensure the "sources" key exists and has at least one file.
    if "sources" not in data:
        return {"status": "failed", "message": "Missing sources key"}, 400
    if not data["sources"]:
        return {"status": "failed", "message": "No sources provided"}, 400

    # Grab the first file from the sources.
    first_source_key, first_source_value = next(iter(data['sources'].items()))
    logging.debug(f"Source key (contract_path): {first_source_key}")
    logging.debug(f"Source value: {first_source_value}")
    
    code = first_source_value.get("content", "")
    
    try:
        out_dict = compile_code(
            code,
            first_source_key,
            output_formats=['abi', 'bytecode', 'bytecode_runtime', 'source_map', 'method_identifiers']
        )
        # Create the artifact object with the expected structure
        artifact = {
            "manifest": "ethpm/3",
            "name": None,
            "version": None,
            "meta": None,
            "sources": {
                first_source_key: {
                    "content": code,
                    "urls": [],
                    "checksum": None,
                    "type": None,
                    "license": None,
                    "references": None,
                    "imports": None
                }
            },
            "contractTypes": {
                first_source_key.split('/')[-1].split('.')[0]: {  # Extract contract name from path
                    "contractName": first_source_key.split('/')[-1].split('.')[0],
                    "sourceId": first_source_key,
                    "deploymentBytecode": {
                        "bytecode": out_dict.get("bytecode", ""),
                        "linkReferences": None,
                        "linkDependencies": None
                    },
                    "runtimeBytecode": {
                        "bytecode": out_dict.get("bytecode_runtime", ""),
                        "linkReferences": None,
                        "linkDependencies": None
                    },
                    "abi": out_dict.get("abi", []),
                    "sourcemap": out_dict.get("source_map", ""),
                    "methodIdentifiers": out_dict.get("method_identifiers", {})
                }
            },
            "compilers": None,
            "deployments": None,
            "buildDependencies": None
        }
        
        return artifact, 200
        
    except VyperException as e:
        error_msg = str(e)
        return {"status": "failed", "message": error_msg}, 400
    except Exception as e:
        error_msg = str(e)
        logging.error(f"Unexpected error during compilation: {error_msg}")
        return {"status": "failed", "message": "Internal compilation error"}, 500

@routes.options('/compile')
async def compile_it_options(request):
    return web.json_response(status=200, headers=headers)

@routes.post('/compile')
async def compile_it(request):
    data = await request.json()
    loop = asyncio.get_event_loop()
    out, status = await loop.run_in_executor(executor_pool, _compile, data)
    # Generate a unique id similar to a temporary hash (with a "tmp" prefix)
    unique_id = "tmp" + str(uuid.uuid4())[:10]
    # Store the result with a status based on the compilation outcome.
    compilation_results[unique_id] = {
        'status': 'SUCCESS' if status == 200 else 'FAILURE',
        'data': out
    }
    return web.json_response(unique_id, status=status, headers=headers)

@routes.get('/status/{id}')
async def check_status(request):
    comp_id = request.match_info['id']
    if comp_id in compilation_results:
        return web.Response(text=compilation_results[comp_id]['status'], status=200, headers=headers)
    else:
        return web.Response(text="NOT FOUND", status=404, headers=headers)

@routes.get('/artifacts/{id}')
async def get_artifacts(request):
    comp_id = request.match_info['id']
    if comp_id in compilation_results:
        return web.json_response(compilation_results[comp_id]['data'], status=200, headers=headers)
    else:
        return web.Response(text="NOT FOUND", status=404, headers=headers)

def main():
    # Configure aiohttp to use charset-normalizer instead of cchardet
    ClientResponse._get_charset = lambda self: None
    app = web.Application()
    
    # Setup CORS
    cors = cors_setup(app, defaults={
        "*": ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })
    
    # Add routes and enable CORS for all of them
    app.add_routes(routes)
    for route in list(app.router.routes()):
        cors.add(route)
    
    logging.basicConfig(level=logging.DEBUG)
    web.run_app(app)

if __name__ == "__main__":
    main()
