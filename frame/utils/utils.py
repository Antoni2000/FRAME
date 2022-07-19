import re
from typing import Any, TextIO
from ruamel.yaml import YAML

Vector = list[float]
Matrix = list[Vector]


def valid_identifier(ident: Any) -> bool:
    """
    Checks whether the argument is a string and is a valid identifier.
    The first character must be a letter or '_'. The remaining characters can also be digits
    :param ident: identifier.
    :return: True if valid, and False otherwise.
    """
    if not isinstance(ident, str):
        return False
    _valid_id = '^[A-Za-z_][A-Za-z0-9_]*'
    return re.fullmatch(_valid_id, ident) is not None


def is_number(n: Any) -> bool:
    """
    Checks whether a value is a number (int or float).
    :param n: the number.
    :return: True if it is a number, False otherwise.
    """
    return isinstance(n, (int, float))


def string_is_number(s: str) -> bool:
    """
    Checks whether a string represents a number.
    :param s: the string.
    :return: True if it represents a number, False otherwise.
    """
    try:
        float(s)
        return True
    except ValueError:
        return False


def read_yaml(stream: str | TextIO) -> str:
    """
    Reads a YAML contents from a file or a string. The distinction between a YAML contents and a file name is
    done by checking that ':' exists in the string
    :param stream: the input. It can be either a file handler, a file name or a YAML contents
    :return: the YAML tree
    """
    if isinstance(stream, str):
        if ':' in stream:
            txt = stream
        else:
            with open(stream) as f:
                txt = f.read()
    else:
        assert isinstance(stream, TextIO)
        txt = stream.read()

    yaml = YAML(typ='safe')
    return yaml.load(txt)
