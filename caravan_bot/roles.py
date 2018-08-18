import enum


class Role(enum.Enum):
    ADMIN = 0
    LEADER = 1
    MEMBER = 2
    ANYONE = 3
