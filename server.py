#!/usr/bin/env python3
import asyncio
import logging
import uuid
from aiohttp import web
from aiohttp.client import ClientResponse

import vyper
from vyper.compiler import compile_code
from vyper.exceptions import VyperException

from concurrent.futures import ThreadPoolExecutor

routes = web.RouteTableDef()
headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "X-Requested-With, Content-type"
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
    if not code:
        return {"status": "failed", "message": "No code provided in sources"}, 400
    if not isinstance(code, str):
        return {"status": "failed", "message": "Code must be a non-empty string"}, 400

    try:
        # Log the parameters being passed to compile_code
        logging.debug(f"Compiling code with contract_path: {first_source_key}")
        
        # Compile the code; request extra outputs as needed.
        out_dict = compile_code(
            code,  # first argument: source_code
            first_source_key,  # second argument: contract_path
            output_formats=['abi', 'bytecode', 'bytecode_runtime', 'ir', 'method_identifiers']
        )
        logging.debug(f"Compilation successful. Output keys: {out_dict.keys()}")
        
        # Convert the IR to a string (if needed)
        out_dict['ir'] = str(out_dict['ir'])
    except VyperException as e:
        logging.error(f"Compilation failed with error: {str(e)}")
        col_offset, lineno = None, None
        if hasattr(e, "col_offset") and hasattr(e, "lineno"):
            col_offset, lineno = e.col_offset, e.lineno
        elif e.annotations and len(e.annotations) > 0:
            ann = e.annotations[0]
            col_offset, lineno = ann.col_offset, ann.lineno
        return {
            'status': 'failed',
            'message': str(e),
            'column': col_offset,
            'line': lineno
        }, 400

    # Derive a contract name from the filename (e.g. "ERC20" from "examples/tokens/ERC20.vy")
    contract_name = (first_source_key.split('/')[-1].split('.')[0]
                     if '.' in first_source_key else "Contract")

    # Build the artifact in the requested format.
    artifact = {
        "manifest": "ethpm/3",
        "name": None,
        "version": None,
        "meta": None,
        "sources": data["sources"],
        "contractTypes": {
            contract_name: {
                "contractName": contract_name,
                "sourceId": first_source_key,
                "deploymentBytecode": {"bytecode": out_dict.get("bytecode", "")},
                "runtimeBytecode": {"bytecode": out_dict.get("bytecode_runtime", "")},
                "abi": out_dict.get("abi", []),
                "sourcemap": out_dict.get("sourcemap", "")
            }
        },
        "pcmap": out_dict.get("pcmap", {}),  # default empty if not provided
        "dev_messages": {},
        "ast": out_dict.get("ast", {}),        # default empty if not provided
        "userdoc": {},
        "devdoc": {},
        "methodIdentifiers": out_dict.get("method_identifiers", {})
    }
    return artifact, 200

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
    app.add_routes(routes)
    logging.basicConfig(level=logging.DEBUG)
    web.run_app(app)

if __name__ == "__main__":
    main()
