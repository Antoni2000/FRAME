"""
Module to represent points, shapes and rectangles
"""

from typing import Any, Union, Sequence, Optional
from dataclasses import dataclass

from frame.utils.keywords import KW_FIXED, KW_CENTER, KW_SHAPE, KW_REGION, KW_NAME, KW_GROUND, KW_BLOCKAGE
from frame.utils.utils import valid_identifier

RectDescriptor = tuple[float, float, float, float, str]  # (x,y,w,h, region)


class Point:
    """
    A class to represent two-dimensional points and operate with them
    """

    _x: float  # x coordinate
    _y: float  # y coordinate

    def __init__(self, x: Union['Point', tuple[float, float], float, None] = None, y: float | None = None) -> None:
        """
        Constructor of a Point. See the example for ways of constructing it
        :param x: a Point or tuple[float, float], a float, or None
        :param y: None if x is a Point, tuple[float, float] or None, or a float if x is a float

        :Example:
        >>> Point()
        Point(x=0, y=0)
        >>> Point(1)
        Point(x=1, y=1)
        >>> Point(1, 2)
        Point(x=1, y=2)
        >>> Point((1, 2))
        Point(x=1, y=2)
        """

        if x is None:  # x and y are None
            self.x, self.y = 0, 0
        elif y is None:  # x is a Point or a number and y is None
            if isinstance(x, Point):
                self.x, self.y = x.x, x.y
            elif isinstance(x, tuple):
                self.x, self.y = x
            else:
                self.x, self.y = x, x
        else:  # x and y are numbers
            assert isinstance(x, (int, float)) and isinstance(y, (int, float))
            self.x, self.y = x, y

    @property
    def x(self) -> float:
        return self._x

    @x.setter
    def x(self, value: float):
        self._x = value

    @property
    def y(self) -> float:
        return self._y

    @y.setter
    def y(self, value: float):
        self._y = value

    def __eq__(self, other: object) -> bool:
        """Return self == other."""
        assert isinstance(other, Point)
        return self.x == other.x and self.y == other.y

    def __neg__(self) -> 'Point':
        """Return -self."""
        return Point(-self.x, -self.y)

    def __add__(self, other: Union['Point', tuple[float, float], float]) -> 'Point':
        """Return self + other."""
        other = Point(other)
        return Point(self.x + other.x, self.y + other.y)

    __radd__ = __add__

    def __sub__(self, other: Union['Point', tuple[float, float], float]) -> 'Point':
        """Return self - other."""
        other = Point(other)
        return Point(self.x, self.y) + -other

    def __rsub__(self, other: Union['Point', tuple[float, float], float]) -> 'Point':
        """Return other - self."""
        other = Point(other)
        return other - self

    def __mul__(self, other: Union['Point', tuple[float, float], float]) -> 'Point':
        """Return self*other using component-wise multiplication. other can either be a number or another point."""
        other = Point(other)
        return Point(self.x * other.x, self.y * other.y)

    __rmul__ = __mul__

    def __pow__(self, exponent: float) -> 'Point':
        """Return self**exponent using component-wise exponentiation."""
        return Point(self.x ** exponent, self.y ** exponent)

    def __truediv__(self, other: Union['Point', tuple[float, float], float]) -> 'Point':
        """Return self / other using component-wise true division. other can either be a number or another point."""
        other = Point(other)
        return Point(self.x / other.x, self.y / other.y)

    def __rtruediv__(self, other: Union['Point', tuple[float, float], float]):
        """Return other / self using component-wise true division. other can either be a number or another point."""
        other = Point(other)
        return Point(other.x / self.x, other.y / self.y)

    def __and__(self, other: 'Point') -> float:
        """Dot product between self and other."""
        return self.x * other.x + self.y * other.y

    def __str__(self) -> str:
        return f"Point(x={self.x}, y={self.y})"

    __repr__ = __str__

    def __iter__(self):
        yield self.x
        yield self.y


@dataclass()
class Shape:
    """
    A class to represent a two-dimensional rectilinear shape (width and height)
    """
    w: float
    h: float


class Rectangle:
    """
    A class to represent a rectilinear rectangle
    """

    def __init__(self, **kwargs: Any):
        """
        Constructor
        :param kwargs: center (Point), shape (Shape), fixed (bool), region (str)
        """

        # Attributes
        self._center: Point = Point(-1, -1)  # Center of the rectangle
        self._shape: Shape = Shape(-1, -1)  # Shape: width and height
        self._fixed: bool = False  # Is the rectangle fixed?
        self._region: str = KW_GROUND  # Region of the layout to which the rectangle belongs to

        # Reading parameters and type checking
        for key, value in kwargs.items():
            assert key in [KW_CENTER, KW_SHAPE, KW_FIXED, KW_REGION, KW_NAME], "Unknown rectangle attribute"
            if key == KW_CENTER:
                assert isinstance(value, Point), "Incorrect point associated to the center of the rectangle"
                self._center = value
            elif key == KW_SHAPE:
                assert isinstance(value, Shape), "Incorrect shape associated to the rectangle"
                assert value.w > 0, "Incorrect rectangle width"
                assert value.h > 0, "Incorrect rectangle height"
                self._shape = value
            elif key == KW_FIXED:
                assert isinstance(value, bool), "Incorrect value for fixed (should be a boolean)"
                self._fixed = value
            elif key == KW_REGION:
                assert valid_identifier(value) or value == KW_BLOCKAGE, \
                    "Incorrect value for region (should be a valid string)"
                self._region = value
            elif key == KW_NAME:
                assert isinstance(value, str), "Incorrect value for rectangle"
                self._name = value
            else:
                assert False  # Should never happen

    # Getter and setter for center
    @property
    def center(self) -> Point:
        return self._center

    @center.setter
    def center(self, p: Point) -> None:
        self._center = p

    # Getter and setter for shape
    @property
    def shape(self) -> Shape:
        return self._shape

    @shape.setter
    def shape(self, shape) -> None:
        self._shape = shape

    @property
    def fixed(self) -> bool:
        return self._fixed

    @fixed.setter
    def fixed(self, value: bool) -> None:
        self._fixed = value

    @property
    def region(self) -> str:
        return self._region

    @region.setter
    def region(self, region: str) -> None:
        self._region = region

    @property
    def bounding_box(self) -> tuple[Point, Point]:
        """
        :return: a tuple ((xmin, ymin), (xmax, ymax))
        """
        half_w, half_h = self.shape.w / 2, self.shape.h / 2
        xmin, xmax = self.center.x - half_w, self.center.x + half_w
        ymin, ymax = self.center.y - half_h, self.center.y + half_h
        return Point(xmin, ymin), Point(xmax, ymax)

    @property
    def vector_spec(self) -> RectDescriptor:
        """Returns a vector specification of the rectangle [x, y, w, h, region]"""
        return self.center.x, self.center.y, self.shape.w, self.shape.h, self.region

    @property
    def area(self) -> float:
        return self._shape.w * self._shape.h

    def point_inside(self, p: Point) -> bool:
        """
        Checks whether a point is inside the rectangle
        :param p: the point
        :return: True if inside, False otherwise
        """
        bb = self.bounding_box
        return bb[0].x <= p.x <= bb[1].x and bb[0].y <= p.y <= bb[1].y

    def is_inside(self, r: 'Rectangle') -> bool:
        """
        Checks whether the rectangle is inside another rectangle
        :param r: the other rectangle
        :return: True if inside, False otherwise
        """
        bb = self.bounding_box
        # It is a rectangle
        bbr = r.bounding_box
        return bb[0].x >= bbr[0].x and bb[0].y >= bbr[0].y and bb[1].x <= bbr[1].x and bb[1].y <= bbr[1].y

    def overlap(self, r: 'Rectangle') -> bool:
        """
        Checks whether two rectangles overlap. They are considered not to overlap if they touch each other
        :param r: the other rectangle.
        :return: True if they overlap, and False otherwise.
        """
        return self.area_overlap(r) > 0

    def area_overlap(self, r: 'Rectangle') -> float:
        """
        Returns the area overlap between the two rectangles
        :param r: the other rectangle
        :return: the area overlap
        """
        ll1, ur1 = self.bounding_box
        ll2, ur2 = r.bounding_box
        minx = max(ll1.x, ll2.x)
        maxx = min(ur1.x, ur2.x)
        if minx >= maxx:
            return 0.0
        miny = max(ll1.y, ll2.y)
        maxy = min(ur1.y, ur2.y)
        if miny >= maxy:
            return 0.0
        return (maxx - minx) * (maxy - miny)

    def duplicate(self) -> 'Rectangle':
        """
        Creates a duplication of the rectangle
        :return: the rectangle
        """
        return Rectangle(**{KW_CENTER: self.center, KW_SHAPE: self.shape, KW_FIXED: self.fixed, KW_REGION: self.region})

    def split_horizontal(self, x: float = -1) -> tuple['Rectangle', 'Rectangle']:
        """
        Splits the rectangle horizontally cutting by x. If x is negative, the rectangle is split into two halves
        :param x: the x-cut
        :return: two rectangles
        """
        if x < 0:
            x = self.center.x
        bb = self.bounding_box
        assert bb[0].x < x < bb[1].x
        c1 = Point((bb[0].x + x) / 2, self.center.y)
        sh1 = Shape(x - bb[0].x, self.shape.h)
        c2 = Point((bb[1].x + x) / 2, self.center.y)
        sh2 = Shape(self.shape.w - sh1.w, self.shape.h)
        r1 = Rectangle(**{KW_CENTER: c1, KW_SHAPE: sh1, KW_REGION: self.region, KW_FIXED: self.fixed})
        r2 = Rectangle(**{KW_CENTER: c2, KW_SHAPE: sh2, KW_REGION: self.region, KW_FIXED: self.fixed})
        return r1, r2

    def split_vertical(self, y: float = -1) -> tuple['Rectangle', 'Rectangle']:
        """
        Splits the rectangle vertically cutting by y. If y is negative, the rectangle is split into two halves
        :param y: the y-cut
        :return: two rectangles
        """
        if y < 0:
            y = self.center.y
        bb = self.bounding_box
        assert bb[0].y < y < bb[1].y
        c1 = Point(self.center.x, (bb[0].y + y) / 2)
        sh1 = Shape(self.shape.w, y - bb[0].y)
        c2 = Point(self.center.x, (bb[1].y + y) / 2)
        sh2 = Shape(self.shape.w, self.shape.h - sh1.h)
        r1 = Rectangle(**{KW_CENTER: c1, KW_SHAPE: sh1, KW_REGION: self.region, KW_FIXED: self.fixed})
        r2 = Rectangle(**{KW_CENTER: c2, KW_SHAPE: sh2, KW_REGION: self.region, KW_FIXED: self.fixed})
        return r1, r2

    def __mul__(self, other: 'Rectangle') -> Optional['Rectangle']:
        """
        Calculates the intersection of two rectangles and returns another rectangle (or None if no intersection).
        If the rectangles belong to different regions, None is returned
        :param other: The other rectangle
        :return: a rectangle representing the intersection (or None if no intersection)
        """
        if self.region != other.region:
            return None
        ll1, ur1 = self.bounding_box
        ll2, ur2 = other.bounding_box
        minx = max(ll1.x, ll2.x)
        maxx = min(ur1.x, ur2.x)
        width = maxx - minx
        if width <= 0:
            return None
        miny = max(ll1.y, ll2.y)
        maxy = min(ur1.y, ur2.y)
        height = maxy - miny
        if height <= 0:
            return None
        center = Point(minx + width / 2, miny + height / 2)
        return Rectangle(**{KW_CENTER: center, KW_SHAPE: Shape(width, height), KW_REGION: self.region})

    def __eq__(self, other: Any) -> bool:
        """
        Checks whether two rectangles are the same (same center, same shape)
        :param other: the other rectangle (potentially another type of object)
        :return: True if equal, and False otherwise
        """
        if not isinstance(other, Rectangle):
            return False
        return self.center == other.center and self.shape == other.shape and self.region == other.region

    def __str__(self) -> str:
        """
        :return: string representation of the rectangle
        """
        s = f"({KW_CENTER}={self.center}, {KW_SHAPE}={self.shape}, {KW_REGION}={self.region}"
        if self.fixed:
            s += f", {KW_FIXED}"
        s += ")"
        return s

    __repr__ = __str__


def parse_yaml_rectangle(r: Sequence[float | int | str], fixed: bool = False) -> Rectangle:
    """Parses a rectangle
    :param r: a YAML description of the rectangle (a tuple or list with 4 numeric values (x, y, w, h)).
    Optionally, it may contain a fifth parameter (string) specifying a region
    :param fixed: Indicates whether the rectangle should be fixed
    :return: a rectangle
    """

    if isinstance(r, list):
        r = tuple(r)
    assert isinstance(r, tuple) and 4 <= len(r) <= 5, f"Incorrect format for rectangle"
    for i in range(4):
        x = r[i]
        assert isinstance(x, (int, float)) and x >= 0, f"Incorrect value for rectangle"
    if len(r) == 5:
        assert isinstance(r[4], str) and valid_identifier(r[4])

    assert isinstance(r[0], (int, float)) and isinstance(r[1], (int, float)) and \
           isinstance(r[2], (int, float)) and isinstance(r[3], (int, float))
    kwargs = {KW_CENTER: Point(r[0], r[1]), KW_SHAPE: Shape(r[2], r[3]), KW_FIXED: fixed}
    if len(r) == 5:
        kwargs[KW_REGION] = r[4]
    return Rectangle(**kwargs)
