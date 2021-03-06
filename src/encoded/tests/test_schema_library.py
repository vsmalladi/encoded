import pytest


def test_library_starting_quantity_post(testapp, library_starting_quantity):
    testapp.post_json('/library', library_starting_quantity)


def test_library_fragmentation_method_string(testapp, library_with_invalid_fragmentation_methods_string):
    res = testapp.post_json('/library', library_with_invalid_fragmentation_methods_string, status=422)


def test_library_fragmentation_method_list(testapp, library_with_valid_fragmentation_method_list):
    testapp.post_json('/library', library_with_valid_fragmentation_method_list, status=201)


def test_library_fragmentation_method_list(testapp, library_with_valid_fragmentation_method_list):
    testapp.post_json('/library', library_with_valid_fragmentation_method_list, status=201)
    library_with_valid_fragmentation_method_list.update({'fragmentation_duration_time': 5})
    testapp.post_json('/library', library_with_valid_fragmentation_method_list, status=422)
    library_with_valid_fragmentation_method_list.update({'fragmentation_duration_time_units': 'minutes'})
    testapp.post_json('/library', library_with_valid_fragmentation_method_list, status=201)
    library_with_valid_fragmentation_method_list.pop('fragmentation_methods')
    testapp.post_json('/library', library_with_valid_fragmentation_method_list, status=422)
