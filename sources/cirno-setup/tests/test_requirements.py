"""Readiness must check every constraint, including repeated dependency paths."""
from email.message import Message
from types import SimpleNamespace

import pytest
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


def test_plain_requirement_checks_missing_and_incompatible_transitive_dependencies():
    from importlib.metadata import PackageNotFoundError

    installed = {'root': distribution('1', ('middle>=2',)),
                 'middle': distribution('2', ('leaf>=3',))}

    def lookup(name):
        if name not in installed:
            raise PackageNotFoundError(name)
        return installed[name]

    assert not requirement_installed('root', lookup=lookup)
    installed['leaf'] = distribution('2')
    assert not requirement_installed('root', lookup=lookup)
    installed['leaf'] = distribution('3')
    assert requirement_installed('root', lookup=lookup)


def test_plain_requirement_keeps_unrequested_extras_optional_and_handles_cycles():
    installed = {'root': distribution('1', ('peer>=1', 'optional; extra == "other"'), ('other',)),
                 'peer': distribution('1', ('root>=2',))}
    assert not requirement_installed('root', lookup=installed.__getitem__)
    installed['peer'] = distribution('1', ('root>=1',))
    assert requirement_installed('root', lookup=installed.__getitem__)



@pytest.mark.parametrize('version', [None, '', 'broken release'])
@pytest.mark.parametrize('requested', ['root', 'root>=1'])
def test_incomplete_distribution_version_is_not_ready(requested, version):
    assert not requirement_installed(requested, lookup=lambda _: distribution(version))


def test_base_dependencies_do_not_prove_an_undeclared_extra_is_installed():
    installed = {'root': distribution('1', ('base>=1',)), 'base': distribution('1')}
    assert requirement_installed('root', lookup=installed.__getitem__)
    assert not requirement_installed('root[missing]', lookup=installed.__getitem__)


def test_legacy_extra_markers_are_checked_even_without_provides_extra():
    installed = {'root': distribution('1', ('base>=1', 'optional>=2; extra == "feature"')),
                 'base': distribution('1'), 'optional': distribution('1')}
    assert not requirement_installed('root[feature]', lookup=installed.__getitem__)
    installed['optional'] = distribution('2')
    assert requirement_installed('root[feature]', lookup=installed.__getitem__)
    assert not requirement_installed('root[missing]', lookup=installed.__getitem__)


def test_declared_extra_without_additional_requirements_is_ready():
    assert requirement_installed('root[empty]', lookup=lambda _: distribution('1', extras=('empty',)))


@pytest.mark.parametrize('raw', ['not a requirement [', 'base; no_such_marker == "true"'])
def test_corrupt_installed_dependency_metadata_is_not_ready(raw):
    assert not requirement_installed('root', lookup=lambda _: distribution('1', (raw,)))
