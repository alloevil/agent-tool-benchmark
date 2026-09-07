"""Small calculator used by the edit-format benchmark."""

VERSION = "1.0.0"


def add(a, b):
    if not isinstance(a, (int, float)):
        raise TypeError("a must be a number")
    return a + b


def subtract(a, b):
    if not isinstance(a, (int, float)):
        raise TypeError("a must be a number")
    return a - b


def multiply(a, b):
    return a * b


def divide(a, b):
    # TODO: handle divide by zero
    return a / b


def apply_op(op, a, b):
    ops = {
        "add": add,
        "sub": subtract,
        "mul": multiply,
        "div": divide,
    }
    if op not in ops:
        raise KeyError(f"unknown op: {op}")
    return ops[op](a, b)


def main():
    import sys

    if len(sys.argv) == 4:
        op, a, b = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
        print(apply_op(op, a, b))


if __name__ == "__main__":
    main()
