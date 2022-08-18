from ctypes import *
from typing import Type


class BOX(Structure):
    _fields_ = ("x1", c_double), \
               ("y1", c_double), \
               ("x2", c_double), \
               ("y2", c_double), \
               ("p", c_double)


class GreedyManager:

    def __init__(self):
        # TODO: HOW DO I GET RID OF THAT "lib.win-amd64-3.10" !??!?!??!!
        # Perhaps I shoud assume we're running this from the build folder instead
        # That would make this so much easier
        # I must inquiry about this issue on a meeting
        libfile = r"..\..\build\lib.win-amd64-3.10\rect_greedy.pyd"
        self.mylib = CDLL(libfile)
        self.mylib.find_best_box.restype = BOX
        self.mylib.find_best_box.argtypes = [POINTER(BOX), c_double, c_double, c_long, c_double]

    def find_best_box(self, ww: float, hh: float, nb: int, pr: float,
                      inboxes: list[tuple[float, float, float, float, float]]) -> \
            tuple[float, float, float, float, float]:
        assert(nb == len(inboxes))

        # First, we cast the inputs into c types
        boxarr: Type[Array[BOX]] = BOX * nb
        inboxrecast = cast(boxarr(*(map(lambda t: BOX(t[0], t[1], t[2], t[3], t[4]), inboxes))), POINTER(BOX))

        w = c_double(ww)
        h = c_double(hh)
        n = c_long(nb)
        p = c_double(pr)

        # Then, we call the solver
        box: BOX = self.mylib.find_best_box(inboxrecast, w, h, n, p)

        # Finally, we return the result
        return box.x1, box.y1, box.x2, box.y2, box.p