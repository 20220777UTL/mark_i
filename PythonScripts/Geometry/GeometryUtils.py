from dis import Positions

import Global
from WorldModel import Params
from . import *
import math
import typing


def getUnitVectorByDir(direction: typing.SupportsFloat) -> "CVector":
    return CVector(math.cos(direction), math.sin(direction))


class Rectangle:
    """
    矩形类，由中心坐标和长宽定义
    """
    def __init__(self, center: CGeoPoint, x: float, y: float):
        """
        初始化矩形
        
        Args:
            center: 矩形中心位置 (CGeoPoint)
            x: 矩形宽度 (沿x轴)
            y: 矩形高度 (沿y轴)
        """
        self.center = center
        self.width = x
        self.height = y
        self.half_width = x / 2.0
        self.half_height = y / 2.0
    
    def isInsideRectangle(self, point: CGeoPoint) -> bool:
        """
        判断一个点是否在矩形内部（包括边界）
        
        Args:
            point: 待判断的点 (CGeoPoint)
            
        Returns:
            bool: 点是否在矩形内部
        """
        dx = abs(point.x() - self.center.x())
        dy = abs(point.y() - self.center.y())
        return dx <= self.half_width and dy <= self.half_height
    
    def project_point_to_boundary(self, point: CGeoPoint) -> CGeoPoint:
        """
        计算一个点在矩形边框上的投影点
        
        如果点已经在矩形内部，返回最近的边界点；
        如果点在外部，返回最近的边界点
        
        Args:
            point: 待投影的点 (CGeoPoint)
            
        Returns:
            CGeoPoint: 投影点在矩形边框上的位置
        """
        # 计算相对于中心的坐标
        rel_x = point.x() - self.center.x()
        rel_y = point.y() - self.center.y()
        
        # 将坐标限制在矩形范围内
        clamped_x = max(-self.half_width, min(self.half_width, rel_x))
        clamped_y = max(-self.half_height, min(self.half_height, rel_y))
        
        # 确定投影点在边界上
        # 如果在矩形内部，投影到最近的边界
        on_left_right_edge = (abs(clamped_x) == self.half_width)
        on_top_bottom_edge = (abs(clamped_y) == self.half_height)
        
        # 如果不在任何边界上，需要将其投影到边界
        if not on_left_right_edge and not on_top_bottom_edge:
            # 计算到四条边的距离
            dist_to_left = self.half_width + rel_x
            dist_to_right = self.half_width - rel_x
            dist_to_bottom = self.half_height + rel_y
            dist_to_top = self.half_height - rel_y
            
            min_dist = min(dist_to_left, dist_to_right, dist_to_bottom, dist_to_top)
            
            if min_dist == dist_to_left:
                clamped_x = -self.half_width
            elif min_dist == dist_to_right:
                clamped_x = self.half_width
            elif min_dist == dist_to_bottom:
                clamped_y = -self.half_height
            else:  # min_dist == dist_to_top
                clamped_y = self.half_height
        
        return CGeoPoint(self.center.x() + clamped_x, self.center.y() + clamped_y)
    
    def get_corners(self) -> typing.List[CGeoPoint]:
        """
        获取矩形的四个顶点
        
        Returns:
            List[CGeoPoint]: 按顺序返回四个顶点 (左下、右下、右上、左上)
        """
        x_min = self.center.x() - self.half_width
        x_max = self.center.x() + self.half_width
        y_min = self.center.y() - self.half_height
        y_max = self.center.y() + self.half_height
        
        return [
            CGeoPoint(x_min, y_min),  # 左下
            CGeoPoint(x_max, y_min),  # 右下
            CGeoPoint(x_max, y_max),  # 右上
            CGeoPoint(x_min, y_max)   # 左上
        ]
    
    def get_unit_vector_to_center(self, point: CGeoPoint) -> CVector:
        """
        获取从矩形外部的点指向矩形中心的单位向量
        
        该向量垂直于矩形的某条边，指向矩形内部
        
        Args:
            point: 矩形外部的点 (CGeoPoint)
            
        Returns:
            CVector: 指向矩形中心的单位向量
        """

        center_dx = self.center.x() - point.x()
        center_dy = self.center.y() - point.y()
        center_length = math.sqrt(center_dx * center_dx + center_dy * center_dy)
        if center_length < 1e-9:
            return CVector(1, 0)
        return CVector(center_dx, center_dy).unit()

