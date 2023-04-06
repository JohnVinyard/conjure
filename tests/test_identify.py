from unittest import TestCase

from conjure.identifier import FunctionContentIdentifier, FunctionNameIdentifier



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
    