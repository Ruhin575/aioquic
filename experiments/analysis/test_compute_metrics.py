import unittest

from compute_metrics import normalize_file_size, size_matches


class TestFileSizeMatching(unittest.TestCase):
    def test_megabytes_matches_decimal_and_binary_sizes(self):
        target = normalize_file_size("10MB")

        self.assertTrue(size_matches("10MB", target))
        self.assertTrue(size_matches(10_000_000, target))
        self.assertTrue(size_matches(10_485_760, target))

    def test_different_file_size_does_not_match(self):
        target = normalize_file_size("10MB")

        self.assertFalse(size_matches("50MB", target))
        self.assertFalse(size_matches(5_000_000, target))

    def test_numeric_size_matches_exactly(self):
        target = normalize_file_size("10485760")

        self.assertTrue(size_matches(10_485_760, target))
        self.assertFalse(size_matches(5_000_000, target))


if __name__ == "__main__":
    unittest.main()
