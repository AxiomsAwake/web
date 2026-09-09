#!/usr/bin/env python3
"""Check an exact staged game at its eventual project/sub-site prefix in Chromium."""
from __future__ import annotations
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from contract import ID, read_json, require


class Handler(SimpleHTTPRequestHandler):
    extensions_map = dict(SimpleHTTPRequestHandler.extensions_map, **{'.wasm': 'application/wasm'})
    def log_message(self, *_):
        pass


def check(url: str, config: dict, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        launch = {'headless': True, 'args': ['--use-angle=swiftshader', '--enable-unsafe-swiftshader']}
        if os.environ.get('CHROMIUM_EXECUTABLE'):
            launch['executable_path'] = os.environ['CHROMIUM_EXECUTABLE']
        browser = playwright.chromium.launch(**launch)
        evidence = []
        try:
            viewports = [{'width': 1366, 'height': 768}]
            if config.get('touch'):
                viewports.append({'width': 390, 'height': 844})
            for viewport in viewports:
                context = browser.new_context(viewport=viewport, has_touch=viewport['width'] < 600,
                                              is_mobile=viewport['width'] < 600)
                try:
                    page = context.new_page()
                    page.set_default_timeout(90000)
                    errors, missing = [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('response', lambda response: missing.append(response.url) if response.status >= 400 and urlparse(response.url).netloc == urlparse(url).netloc and not response.url.endswith('/favicon.ico') else None)
                    response = page.goto(url, wait_until='domcontentloaded')
                    require(response is not None and response.ok, 'Entrypoint HTTP failure')
                    selector = config.get('ready_selector', 'body')
                    page.locator(selector).first.wait_for(state='visible')
                    if config.get('wait_hidden'):
                        page.locator(config['wait_hidden']).wait_for(state='hidden')
                    if config.get('dismiss') and page.locator(config['dismiss']).is_visible():
                        page.locator(config['dismiss']).click()
                    for step in config.get('steps', []):
                        if 'click' in step:
                            loc = page.locator(step['click']).first
                            loc.scroll_into_view_if_needed()
                            loc.tap() if viewport['width'] < 600 else loc.click()
                        elif 'press' in step:
                            page.keyboard.press(step['press'])
                        else:
                            raise ValueError('Unknown smoke interaction')
                    page.wait_for_timeout(1500)
                    if config.get('assert_selector'):
                        page.locator(config['assert_selector']).first.wait_for(state='visible')
                    require(not errors, 'Browser runtime errors: ' + '; '.join(errors))
                    require(not missing, 'Missing same-origin assets: ' + '; '.join(missing))
                    page.screenshot(path=str(output / f"{viewport['width']}.png"))
                    # Same context: verifies reload rather than only an empty browser cache.
                    page.reload(wait_until='domcontentloaded')
                    page.locator(selector).first.wait_for(state='visible')
                    if config.get('wait_hidden'):
                        page.locator(config['wait_hidden']).wait_for(state='hidden')
                    page.wait_for_timeout(500)
                    require(not errors and not missing, 'Reload failed')
                    evidence.append({'viewport': viewport, 'url': url, 'runtime_errors': errors, 'missing_assets': missing, 'reload': 'passed'})
                except Exception:
                    try:
                        page.screenshot(path=str(output / f"failed-{viewport['width']}.png"), timeout=5000)
                    except Exception:
                        pass
                    raise
                finally:
                    context.close()
        finally:
            browser.close()
    report = {'scope': 'startup, declared UI steps, prefix assets and cached reload; not full gameplay or physical-device certification', 'browser': 'Chromium', 'checks': evidence}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', required=True)
    parser.add_argument('--payload', type=Path)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--url')
    parser.add_argument('--output', type=Path, default=Path('smoke-evidence'))
    args = parser.parse_args()
    require(bool(ID.fullmatch(args.site)), 'Invalid site')
    candidate = read_json(args.candidate)
    config = candidate.get('smoke', {})
    if args.url:
        print(json.dumps(check(args.url, config, args.output)))
        return
    require(args.payload is not None, 'Need a payload or public URL')
    with tempfile.TemporaryDirectory(prefix='axioms-prefix-') as temp:
        root = Path(temp)
        shutil.copytree(args.payload, root / 'web' / args.site)
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(root)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            print(json.dumps(check(f'http://127.0.0.1:{server.server_port}/web/{args.site}/', config, args.output)))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    main()
