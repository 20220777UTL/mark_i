import Utils
from Geometry import *
from Vision import Ball
from WorldModel import Params


def generateShootPoint(dist):
    """
    （是一个可以击球的点）球与门的3点一线
    用于辅助Shoot skill，在调用的时候。来自于task.lua中的shootGen
    :param dist: 距离球的长度
    :return:
    """
    goalPos = CGeoPoint(Params.pitchLength / 2, 0)
    pos = Ball.pos() + Utils.Polar2Vector(dist, (Ball.pos() - goalPos).dir())
    return pos
