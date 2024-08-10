from dataclasses import dataclass
from functools import lru_cache
from typing import List, Callable, Optional, Tuple


@dataclass
class Rotor:
    size: int
    increment: int
    erotor: List[int]
    drotor: List[int]


class RotorFactory:
    @staticmethod
    def create(size: int, rand: Callable[[int], int]) -> Rotor:
        erotor = list(range(size + 1))
        drotor = list(range(size + 1))
        increment = 1 + 2 * rand(size // 2)
        erotor[size] = drotor[size] = increment

        for i in range(size - 1, 0, -1):
            r = rand(i + 1)
            erotor[r], erotor[i] = erotor[i], erotor[r]
            drotor[erotor[i]] = i
        drotor[erotor[0]] = 0

        return Rotor(size=size, increment=increment, erotor=erotor, drotor=drotor)


class NewRotor:
    def __init__(self, key: str, n_rotors: int = 6):
        self.key = key
        self.n_rotors = n_rotors
        self.rotors: Optional[Tuple[List[Rotor], List[Rotor], int, List[int]]] = None
        self.positions: List[Optional[List[int]]] = [None, None]

    def encrypt(self, buffer: bytes) -> bytes:
        self.positions[0] = None
        return self._crypt(buffer, False)

    def decrypt(self, buffer: bytes) -> bytes:
        self.positions[1] = None
        return self._crypt(buffer, True)

    def _crypt(self, buffer: bytes, do_decrypt: bool) -> bytes:
        size, rotors, pos = self._get_rotors(do_decrypt)
        out_buffer = bytearray()
        for c in buffer:
            if do_decrypt:
                for rotor in reversed(rotors):
                    c = pos[rotor.size - 1] ^ rotor.drotor[c]
            else:
                for rotor in rotors:
                    c = rotor.erotor[c ^ pos[rotor.size - 1]]
            out_buffer.append(c)
            carry = 0
            for i, rotor in enumerate(rotors):
                pnew = pos[i] + rotor.increment + carry
                pos[i] = pnew % size
                carry = pnew >= size

        return bytes(out_buffer)

    def _get_rotors(self, do_decrypt: bool) -> Tuple[int, List[Rotor], List[int]]:
        if self.rotors is None:
            self._initialize_rotors()

        assert self.rotors is not None
        e_rotors, d_rotors, size, initial_positions = self.rotors

        if self.positions[do_decrypt] is None:
            self.positions[do_decrypt] = initial_positions.copy()

        positions = self.positions[do_decrypt]
        assert positions is not None

        return size, d_rotors if do_decrypt else e_rotors, positions

    def _initialize_rotors(self) -> None:
        size = 256
        rand = self._random_func()
        rotor_factory = RotorFactory()

        e_rotors = []
        d_rotors = []
        positions = [rand(size) for _ in range(self.n_rotors)]

        for _ in range(self.n_rotors):
            rotor = rotor_factory.create(size, rand)
            e_rotors.append(rotor)
            d_rotors.append(Rotor(size, rotor.increment, rotor.drotor, rotor.erotor))

        self.rotors = (e_rotors, d_rotors, size, positions)

    @lru_cache(maxsize=1)
    def _random_func(self) -> Callable[[int], int]:
        mask = 0xFFFF
        x, y, z = 995, 576, 767

        for c in map(ord, self.key):
            x = ((x << 3 | x >> 13) + c) & mask
            y = ((y << 3 | y >> 13) ^ c) & mask
            z = ((z << 3 | z >> 13) - c) & mask

        max_pos = mask >> 1
        mask += 1
        x -= mask if x > max_pos else 0
        y -= mask if y > max_pos else 0
        z -= mask if z > max_pos else 0

        y |= 1

        x = 171 * (x % 177) - 2 * (x // 177)
        y = 172 * (y % 176) - 35 * (y // 176)
        z = 170 * (z % 178) - 63 * (z // 178)

        x += 30269 if x < 0 else 0
        y += 30307 if y < 0 else 0
        z += 30323 if z < 0 else 0

        def rand(n: int, seed: List[Tuple[int, int, int]] = [(x, y, z)]) -> int:
            nonlocal x, y, z
            x, y, z = seed[0]
            seed[0] = ((171 * x) % 30269, (172 * y) % 30307, (170 * z) % 30323)
            return int(((x / 30269 + y / 30307 + z / 30323) * n) % n)

        return rand
