{
    "name": "write_sandbox_file",
    "arguments": {
        "filename": "solution.py",
        "content": "n_terms = 1000000\n\ndef series_sum(terms):\n    total = 0\n    for i in range(terms):\n        if i % 2 == 0:\n            total += 1 / (2 * i + 1)\n        else:\n            total -= 1 / (2 * i + 1)\n    return total\n\ndef calculate():
\\n    result = series_sum(n_terms)\n    print(4 * result)\n\nif __name__ == '__main__':\ncalculate()"
    }
}

{"name": "run_sandbox_python_file", "arguments": {"filename": "solution.py"}}