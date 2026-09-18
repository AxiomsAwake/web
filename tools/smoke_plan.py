"""Bounded same-subpath browser routes; no JavaScript, arbitrary URL or filesystem inputs."""
import re
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
