import unittest

from fixture import greet


class GreetTest(unittest.TestCase):
    def test_greet(self) -> None:
        self.assertEqual(greet("example"), "hello, example")


if __name__ == "__main__":
    unittest.main()
