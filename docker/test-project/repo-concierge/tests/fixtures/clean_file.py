"""Test fixture: clean Python file with no risky patterns."""


def hello():
    """Print a greeting."""
    print("Hello, world!")


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


if __name__ == "__main__":
    hello()
