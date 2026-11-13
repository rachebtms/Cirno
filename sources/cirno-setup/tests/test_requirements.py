"""Readiness must check every constraint, including repeated dependency paths."""
from email.message import Message
from types import SimpleNamespace

from cirno_setup.requirements import requirement_installed


def distribution(version, requires=(), extras=()):
    metadata = Message()
    for extra in extras:
        metadata['Provides-Extra'] = extra
    return SimpleNamespace(version=version, requires=list(requires), metadata=metadata)


def test_repeated_dependency_still_checks_each_extra_constraint():
    installed = {
        'root': distribution('1', ('shared>=1; extra == "a"', 'shared>=2; extra == "b"'), ('a', 'b')),
        'shared': distribution('1.5'),
    }
    assert not requirement_installed('root[a,b]', lookup=installed.__getitem__)
    installed['shared'] = distribution('2')
    assert requirement_installed('root[a,b]', lookup=installed.__getitem__)


def test_cycle_stops_expansion_but_checks_the_returning_version_constraint():
    installed = {
        'root': distribution('1', ('peer[a]',), ('a',)),
        'peer': distribution('1', ('root[a]>=2',), ('a',)),
    }
    assert not requirement_installed('root[a]', lookup=installed.__getitem__)
    installed['peer'] = distribution('1', ('root[a]>=1',), ('a',))
    assert requirement_installed('root[a]', lookup=installed.__getitem__)
