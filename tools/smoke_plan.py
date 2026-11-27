"""Bounded same-subpath browser routes; no JavaScript, arbitrary URL or filesystem inputs."""
import re
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def plan(base_url, config):
    base = urlsplit(base_url)
    if base.scheme not in ('http', 'https') or not base.netloc:
        raise ValueError('Browser smoke needs an HTTP(S) URL')
    routes = config.get('routes', [])
    if not isinstance(routes, list) or len(routes) > 8:
        raise ValueError('At most eight extra browser routes are allowed')
    defaults = {key: value for key, value in config.items() if key != 'routes'}
    result = [('default', base_url, defaults)]
    names = {'default'}
    for route in routes:
        if not isinstance(route, dict) or set(route) - {'name', 'query', 'steps', 'assert_selector'}:
            raise ValueError('Unknown browser route fields')
        name = route.get('name', '')
        if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', name) or name in names:
            raise ValueError('Route names must be unique safe identifiers')
        names.add(name)
        query = route.get('query', {})
        if not isinstance(query, dict) or len(query) > 8:
            raise ValueError('Route query must be a bounded object')
        for key, value in query.items():
            if not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,47}', key) or not isinstance(value, str) or len(value) > 100:
                raise ValueError('Invalid route query')
        options = dict(defaults, steps=route.get('steps', []))
        if 'assert_selector' in route:
            options['assert_selector'] = route['assert_selector']
        address = urlunsplit((base.scheme, base.netloc, base.path,
                              urlencode(dict(parse_qsl(base.query), **query)), ''))
        result.append((name, address, options))
    return result


def console_is_error(kind, message):
    # Godot warnings can use stderr. Actual engine errors and console.error remain fatal.
    return kind == 'error' and not message.lstrip().startswith('WARNING:')


# Generated Player startup hides #status with CSS before engine startup, then
# writes inline display:none only after await engine.startGame().
PLAYER_ENGINE_READY = 'body:has(#status[style*="display: none"]) #canvas'

def staged_smoke_config(site, candidate, payload, config):
    """Strengthen the legacy selector for the already admitted threaded Player stage.

    Package/source authentication and payload staging happen before this call;
    this does not replace those checks or rehash the same package again.
    """
    if site != 'the-keepers' or payload is None or config.get('ready_selector') != '#canvas' or config.get('wait_hidden') != '#status':
        return config
    path = Path(payload) / 'build.json'
    if not path.is_file():
        return config  # Supported legacy Godot packages have no startup declaration.
    build = json.loads(path.read_text())
    startup = build.get('webStartup')
    if startup is None:
        return config
    valid = (startup == 'thread-capable' and build.get('schema') == 'keepers-player-release-build/v1'
             and build.get('target') == 'web' and build.get('mode') in ('player', 'player-demo')
             and build.get('selected', {}).get('id') == 'player'
             and candidate.get('site') == site and candidate.get('source') == 'AxiomsAwake/TheKeepers'
             and candidate.get('package_kind') == 'release-asset'
             and bool(re.fullmatch(r'[a-f0-9]{40}', candidate.get('source_sha', '')))
             and build.get('releaseSource') == candidate['source_sha']
             and build.get('source_revision') == candidate['source_sha'])
    if not valid:
        raise ValueError('Unsupported or unbound Player startup identity')
    return dict(config, ready_selector=PLAYER_ENGINE_READY)
