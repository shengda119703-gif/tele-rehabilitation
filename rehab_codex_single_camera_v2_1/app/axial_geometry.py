"""Whole-head/trunk image-plane proxies; never segmental spinal ROM.

Pixel-length guards reject unresolved reference lines. They are engineering
gates, not evidence of anatomical accuracy, safety or in-plane movement.
"""
import math


def vector(a, b):
    return (b[0]-a[0], b[1]-a[1])


def relative_angle(a, b, minimum_a, minimum_b):
    if not all(math.isfinite(v) for v in (*a, *b)):
        return None
    if math.hypot(*a) < minimum_a or math.hypot(*b) < minimum_b:
        return None
    return math.degrees(math.atan2(a[0]*b[1]-a[1]*b[0], a[0]*b[0]+a[1]*b[1]))


def head_roll(left_shoulder, right_shoulder, left_eye, right_eye):
    return relative_angle(vector(left_shoulder, right_shoulder), vector(left_eye, right_eye), 40., 12.)


def head_pitch(ear, eye):
    # Fixed image horizontal avoids requiring the hip for a head/neck task.
    # A baseline removes fixed camera roll; camera movement during the task still
    # invalidates interpretation and is described as a product limitation.
    return relative_angle((1., 0.), vector(ear, eye), 1., 12.)


def trunk_frontal(left_hip, right_hip, left_shoulder, right_shoulder):
    hips = tuple((left_hip[i]+right_hip[i])/2 for i in (0, 1))
    shoulders = tuple((left_shoulder[i]+right_shoulder[i])/2 for i in (0, 1))
    if math.dist(left_shoulder, right_shoulder) < 40.:
        return None
    return relative_angle(vector(left_hip, right_hip), vector(hips, shoulders), 30., 50.)


def trunk_sagittal(hip, shoulder):
    # Fixed image vertical only; the baseline removes a fixed camera roll, not
    # movement of the camera during a task, pelvic movement or hip contribution.
    return relative_angle((0., -1.), vector(hip, shoulder), 1., 50.)
