"""Runner script: invokes the test_account.py suite via unittest."""
import io
import sys
import unittest
import contextlib

# Load the test module
loader = unittest.TestLoader()
suite = loader.loadTestsFromName("test_account")
stream = io.StringIO()
runner = unittest.TextTestRunner(verbosity=2, stream=stream)
result = runner.run(suite)

output = stream.getvalue()
with open("_test_results.txt", "w") as f:
    f.write(output)
    f.write(f"\n\nSuccess: {result.wasSuccessful()}\n")
    f.write(f"Tests run: {result.testsRun}\n")
    f.write(f"Failures: {len(result.failures)}\n")
    f.write(f"Errors: {len(result.errors)}\n")

# Also print to stdout
print(output)
print(f"Success: {result.wasSuccessful()}")
print(f"Tests run: {result.testsRun}")
print(f"Failures: {len(result.failures)}")
print(f"Errors: {len(result.errors)}")
sys.exit(0 if result.wasSuccessful() else 1)
