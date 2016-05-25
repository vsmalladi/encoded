# Use workbook fixture from BDD tests (including elasticsearch)
from .features.conftest import app_settings, app, workbook
from webob.multidict import MultiDict
import pytest


# Integration tests


def test_search_view(workbook, testapp):
    res = testapp.get('/search/').json
    assert res['@type'] == ['Search']
    assert res['@id'] == '/search/'
    assert res['@context'] == '/terms/'
    assert res['notification'] == 'Success'
    assert res['title'] == 'Search'
    assert res['total'] > 0
    assert 'facets' in res
    assert 'filters' in res
    assert 'columns' in res
    assert '@graph' in res


def test_report_view(workbook, testapp):
    res = testapp.get('/report/?type=Experiment').json
    assert res['@type'] == ['Report']
    assert res['@id'] == '/report/?type=Experiment'
    assert res['@context'] == '/terms/'
    assert res['notification'] == 'Success'
    assert res['title'] == 'Report'
    assert res['total'] > 0
    assert 'facets' in res
    assert 'filters' in res
    assert 'columns' in res
    assert '@graph' in res


def test_matrix_view(workbook, testapp):
    res = testapp.get('/matrix/?type=Experiment').json
    assert res['@type'] == ['Matrix']
    assert res['@id'] == '/matrix/?type=Experiment'
    assert res['@context'] == '/terms/'
    assert res['notification'] == 'Success'
    assert res['title'] == 'Experiment Matrix'
    assert res['total'] > 0
    assert 'facets' in res
    assert 'filters' in res
    assert 'matrix' in res
    assert res['matrix']['max_cell_doc_count'] > 0
    assert res['matrix']['search_base'] == '/search/?type=Experiment'
    assert res['matrix']['x']['group_by'] == 'assay_title'
    assert res['matrix']['x']['label'] == 'Assay'
    assert res['matrix']['x']['limit'] == 20
    assert len(res['matrix']['x']['buckets']) > 0
    assert len(res['matrix']['x']['facets']) > 0
    assert res['matrix']['y']['group_by'] == [
        'replicates.library.biosample.biosample_type', 'biosample_term_name']
    assert res['matrix']['y']['label'] == 'Biosample'
    assert res['matrix']['y']['limit'] == 5
    assert len(res['matrix']['y'][
        'replicates.library.biosample.biosample_type']['buckets']) > 0
    assert len(res['matrix']['y'][
        'replicates.library.biosample.biosample_type']['buckets'][0][
        'biosample_term_name']['buckets']) > 0


# Unit tests


class FakeRequest(object):
    path = '/search/'

    def __init__(self, params):
        self.params = MultiDict(params)


def test_set_filters():
    from encoded.search import set_filters

    request = FakeRequest((
        ('field1', 'value1'),
    ))
    query = {
        'filter': {
            'and': {
                'filters': [],
            },
        },
    }
    result = {'filters': []}
    used_filters = set_filters(request, query, result)

    assert used_filters == {'field1': ['value1']}
    assert query == {
        'filter': {
            'and': {
                'filters': [
                    {
                        'terms': {
                            'embedded.field1.raw': ['value1'],
                        },
                    },
                ],
            },
        },
    }
    assert result == {
        'filters': [
            {
                'field': 'field1',
                'term': 'value1',
                'remove': '/search/?'
            }
        ]
    }


def test_set_filters_searchTerm():
    from encoded.search import set_filters

    request = FakeRequest((
        ('searchTerm', 'value1'),
    ))
    query = {
        'filter': {
            'and': {
                'filters': [],
            },
        },
    }
    result = {'filters': []}
    used_filters = set_filters(request, query, result)

    assert used_filters == {}
    assert query == {
        'filter': {
            'and': {
                'filters': [],
            },
        },
    }
    assert result == {
        'filters': [
            {
                'field': 'searchTerm',
                'term': 'value1',
                'remove': '/search/?'
            }
        ]
    }


# Reserved params should NOT act as filters
@pytest.mark.parametrize('param', [
    'type', 'limit', 'y.limit', 'x.limit', 'mode', 'annotation',
    'format', 'frame', 'datastore', 'field', 'region', 'genome',
    'sort', 'from', 'referrer'])
def test_set_filters_reserved_params(param):
    from encoded.search import set_filters

    request = FakeRequest((
        (param, 'foo'),
    ))
    query = {
        'filter': {
            'and': {
                'filters': [],
            },
        },
    }
    result = {'filters': []}
    used_filters = set_filters(request, query, result)

    assert used_filters == {}
    assert query == {
        'filter': {
            'and': {
                'filters': [],
            },
        },
    }
    assert result == {
        'filters': [],
    }


def test_set_filters_multivalued():
    from encoded.search import set_filters

    request = FakeRequest((
        ('field1', 'value1'),
        ('field1', 'value2'),
    ))
    query = {
        'filter': {
            'and': {
                'filters': [],
            },
        },
    }
    result = {'filters': []}
    used_filters = set_filters(request, query, result)

    assert used_filters == {'field1': ['value1', 'value2']}
    assert query == {
        'filter': {
            'and': {
                'filters': [
                    {
                        'terms': {
                            'embedded.field1.raw': ['value1', 'value2'],
                        },
                    },
                ],
            },
        },
    }
    assert result == {
        'filters': [
            {
                'field': 'field1',
                'term': 'value1',
                'remove': '/search/?field1=value2'
            },
            {
                'field': 'field1',
                'term': 'value2',
                'remove': '/search/?field1=value1'
            }
        ]
    }


def test_set_filters_negated():
    from encoded.search import set_filters

    request = FakeRequest((
        ('field1!', 'value1'),
    ))
    query = {
        'filter': {
            'and': {
                'filters': [],
            },
        },
    }
    result = {'filters': []}
    used_filters = set_filters(request, query, result)

    assert used_filters == {'field1!': ['value1']}
    assert query == {
        'filter': {
            'and': {
                'filters': [
                    {
                        'not': {
                            'terms': {
                                'embedded.field1.raw': ['value1'],
                            },
                        },
                    },
                ],
            },
        },
    }
    assert result == {
        'filters': [
            {
                'field': 'field1!',
                'term': 'value1',
                'remove': '/search/?'
            },
        ],
    }


def test_set_filters_audit():
    from encoded.search import set_filters

    request = FakeRequest((
        ('audit.foo', 'value1'),
    ))
    query = {
        'filter': {
            'and': {
                'filters': [],
            },
        },
    }
    result = {'filters': []}
    used_filters = set_filters(request, query, result)

    assert used_filters == {'audit.foo': ['value1']}
    assert query == {
        'filter': {
            'and': {
                'filters': [
                    {
                        'terms': {
                            'audit.foo': ['value1'],
                        },
                    },
                ],
            },
        },
    }
    assert result == {
        'filters': [
            {
                'field': 'audit.foo',
                'term': 'value1',
                'remove': '/search/?'
            },
        ],
    }


def test_set_facets():
    from collections import OrderedDict
    from encoded.search import set_facets
    facets = [
        ('type', {'title': 'Type'}),
        ('audit.foo', {'title': 'Audit'}),
        ('facet1', {'title': 'Facet 1'}),
    ]
    used_filters = OrderedDict((
        ('facet1', ['value1']),
        ('audit.foo', ['value2']),
    ))
    principals = ['group.admin']
    doc_types = ['Experiment']
    aggs = set_facets(facets, used_filters, principals, doc_types)

    assert {
        'type': {
            'aggs': {
                'type': {
                    'terms': {
                        'field': 'embedded.@type.raw',
                        'exclude': ['Item'],
                        'min_doc_count': 0,
                        'size': 100,
                    },
                },
            },
            'filter': {
                'bool': {
                    'must': [
                        {'terms': {'principals_allowed.view': ['group.admin']}},
                        {'terms': {'embedded.@type.raw': ['Experiment']}},
                        {'terms': {'embedded.facet1.raw': ['value1']}},
                        {'terms': {'audit.foo': ['value2']}},
                    ],
                },
            },
        },
        'audit-foo': {
            'aggs': {
                'audit-foo': {
                    'terms': {
                        'field': 'audit.foo',
                        'min_doc_count': 0,
                        'size': 100,
                    },
                },
            },
            'filter': {
                'bool': {
                    'must': [
                        {'terms': {'principals_allowed.view': ['group.admin']}},
                        {'terms': {'embedded.@type.raw': ['Experiment']}},
                        {'terms': {'embedded.facet1.raw': ['value1']}},
                    ],
                },
            },
        },
        'facet1': {
            'aggs': {
                'facet1': {
                    'terms': {
                        'field': 'embedded.facet1.raw',
                        'min_doc_count': 0,
                        'size': 100,
                    },
                },
            },
            'filter': {
                'bool': {
                    'must': [
                        {'terms': {'principals_allowed.view': ['group.admin']}},
                        {'terms': {'embedded.@type.raw': ['Experiment']}},
                        {'terms': {'audit.foo': ['value2']}},
                    ],
                },
            },
        }
    } == aggs


def test_set_facets_negated_filter():
    from collections import OrderedDict
    from encoded.search import set_facets
    facets = [
        ('facet1', {'title': 'Facet 1'}),
    ]
    used_filters = OrderedDict((
        ('field2!', ['value1']),
    ))
    principals = ['group.admin']
    doc_types = ['Experiment']
    aggs = set_facets(facets, used_filters, principals, doc_types)

    assert {
        'facet1': {
            'aggs': {
                'facet1': {
                    'terms': {
                        'field': 'embedded.facet1.raw',
                        'min_doc_count': 0,
                        'size': 100,
                    },
                },
            },
            'filter': {
                'bool': {
                    'must': [
                        {'terms': {'principals_allowed.view': ['group.admin']}},
                        {'terms': {'embedded.@type.raw': ['Experiment']}},
                        {'not': {'terms': {'embedded.field2.raw': ['value1']}}},
                    ],
                },
            },
        }
    } == aggs


def test_set_facets_nested():
    from encoded.search import set_facets
    facets = [
        ('award.project', {
            'title': 'Project',
            'facets': {
                'award.rfa': {'title': 'RFA'},
            }
        })
    ]
    used_filters = {}
    principals = ['group.admin']
    doc_types = ['Experiment']
    aggs = set_facets(facets, used_filters, principals, doc_types)

    assert {
        'award-project': {
            'aggs': {
                'award-project': {
                    'terms': {
                        'field': 'embedded.award.project.raw',
                        'min_doc_count': 0,
                        'size': 100,
                    },
                    'aggs': {
                        'award-rfa': {
                            'terms': {
                                'field': 'embedded.award.rfa.raw',
                                'min_doc_count': 0,
                                'size': 100,
                            }
                        }
                    }
                },
            },
            'filter': {
                'bool': {
                    'must': [
                        {'terms': {'principals_allowed.view': ['group.admin']}},
                        {'terms': {'embedded.@type.raw': ['Experiment']}},
                    ],
                },
            },
        }
    } == aggs
