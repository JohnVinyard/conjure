import json
from unittest import TestCase

from conjure.identifier import FunctionContentIdentifier, FunctionNameIdentifier, ParamsHash, ParamsJSON


class TestParamsIdentifier(TestCase):

    def test_identical_arguments_produce_identical_names(self):
        identifier = ParamsHash()
        a = identifier.derive_name(1, 'a', [], key1=set(), key2=dict(pony=10))
        b = identifier.derive_name(1, 'a', [], key1=set(), key2=dict(pony=10))
        self.assertEqual(a, b)
    
    def test_different_arguments_produce_different_names(self):
        identifier = ParamsHash()
        a = identifier.derive_name(1, 'a', [], key1=set(), key2=dict(pony=10))
        b = identifier.derive_name(1, 'a', [], key1=set(), key2=dict(pony=11))
        self.assertNotEqual(a, b)
    
    def test_json_namer_raises_for_args(self):
        identifier = ParamsJSON()
        self.assertRaises(ValueError, lambda: identifier.derive_name(1, 'a', key=[]))
    
    def test_json_namer_produces_json(self):
        identifier = ParamsJSON()
        a = identifier.derive_name(key1=[], key2='string')

        hydrated = json.loads(a)
        self.assertIsInstance(hydrated['key1'], list)
        self.assertEqual(len(hydrated['key1']), 0)
        self.assertEqual(hydrated['key2'], 'string')


class TestFunctionIdentifier(TestCase):

    def test_identifies_function_by_name(self):
        def func():
            pass

        identifier = FunctionNameIdentifier()
        name = identifier.derive_name(func)

        self.assertEqual('func', name)
    

    def test_identical_functions_have_same_identifier(self):
        identifier = FunctionContentIdentifier()

        def func():
            a = 10
            b = 12
            return a + b
        
        name1 = identifier.derive_name(func)


        def func():
            a = 10
            b = 12
            return a + b
        
        name2 = identifier.derive_name(func)


        self.assertEqual(name1, name2)
    

    def test_different_functions_have_different_idenitfiers(self):
        identifier = FunctionContentIdentifier()

        def func():
            a = 10
            b = 12
            return a + b
        
        name1 = identifier.derive_name(func)


        def func():
            a = 10
            b = 12
            print(a, b)
            return a + b
        
        name2 = identifier.derive_name(func)


        self.assertNotEqual(name1, name2)
    