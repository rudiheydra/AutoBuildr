"""Check DSPy signature field types."""
import dspy
from api.dspy_signatures import SpecGenerationSignature

print("input_fields type:", type(SpecGenerationSignature.input_fields))
print("output_fields type:", type(SpecGenerationSignature.output_fields))
print()
print("input_fields:", SpecGenerationSignature.input_fields)
print()
print("output_fields:", SpecGenerationSignature.output_fields)
