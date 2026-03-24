import sys, math, random
from dataclasses import dataclass
from typing import List, Tuple
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

SW, SH = 1280, 720
FOV = 65.0
NEAR, FAR = 0.1, 400.0
FPS = 60

LANE_W = 2.8
LANE_COUNT = 3
TRACK_W = LANE_W * LANE_COUNT
TRACK_SEG_LEN = 8.0
TRACK_SEGS = 40
VISIBLE_SEGS = 28

CAM_DIST = 7.5
CAM_HEIGHT = 3.2
CAM_LOOK_AHEAD = 6.0

PLAYER_Y_GROUND = 0.0
PLAYER_Y_JUMP = 3.4
JUMP_DUR = 0.52
SLIDE_DUR = 0.55
LANE_SWITCH_SPD = 9.0

BASE_SPEED = 14.0
MAX_SPEED = 42.0
SPEED_ACCEL = 0.012

OBSTACLE_GAP = 18.0

C_ROAD = (0.06, 0.06, 0.10)
C_ROAD_LINE = (0.10, 0.95, 0.85)
C_ROAD_EDGE = (0.95, 0.10, 0.60)
C_SKY_TOP = (0.20, 0.30, 0.60)
C_SKY_MID = (0.40, 0.50, 0.90)
C_GRID = (0.50, 0.30, 0.80)
C_PLAYER = (0.20, 0.85, 1.00)
C_PLAYER_GLOW = (0.05, 0.50, 0.90)
C_OBSTACLE_A = (0.95, 0.20, 0.20)
C_OBSTACLE_B = (0.95, 0.65, 0.10)
C_COIN = (1.00, 0.90, 0.10)
C_SHIELD = (0.20, 0.80, 1.00)
C_MAGNET = (0.90, 0.30, 1.00)
C_DOUBLE = (1.00, 0.55, 0.10)
C_TRAIL = (0.15, 0.75, 1.00)
C_DRONE = (1.00, 0.25, 0.25)
C_BUILDING = [
    (0.20, 0.15, 0.35),
    (0.25, 0.10, 0.40),
    (0.15, 0.20, 0.45),
]
C_BUILDING_WIN = [
    (0.10, 0.95, 0.85),
    (0.95, 0.20, 0.60),
    (0.95, 0.80, 0.10),
]

DIFFICULTY_PRESETS = {
    1: {
        "name": "EASY",
        "speed_mult": 0.8,
        "max_speed_mult": 0.8,
        "obstacle_gap_mult": 1.5,
        "pattern_weights": {
            "single": 0.5,
            "double": 0.2,
            "zigzag": 0.1,
            "flying": 0.1,
            "spikes": 0.1,
        },
        "drone_count_factor": 0.7,
        "accel_mult": 0.8,
    },
    2: {
        "name": "MEDIUM",
        "speed_mult": 1.0,
        "max_speed_mult": 1.0,
        "obstacle_gap_mult": 1.0,
        "pattern_weights": {
            "single": 0.4,
            "double": 0.25,
            "zigzag": 0.15,
            "flying": 0.15,
            "spikes": 0.05,
        },
        "drone_count_factor": 1.0,
        "accel_mult": 1.0,
    },
    3: {
        "name": "HARD",
        "speed_mult": 1.2,
        "max_speed_mult": 1.2,
        "obstacle_gap_mult": 0.7,
        "pattern_weights": {
            "single": 0.2,
            "double": 0.3,
            "zigzag": 0.2,
            "flying": 0.2,
            "spikes": 0.1,
        },
        "drone_count_factor": 1.5,
        "accel_mult": 1.2,
    },
}


def lane_x(lane: int) -> float:
    return (lane - 1) * LANE_W


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def lerp(a, b, t):
    return a + (b - a) * clamp(t, 0, 1)


def deg2rad(d):
    return d * math.pi / 180.0


@dataclass
class Particle:
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    life: float
    max_life: float
    r: float
    g: float
    b: float
    size: float = 3.0


class Particles:
    def __init__(self):
        self.p: List[Particle] = []

    def emit(self, x, y, z, vx, vy, vz, life, col, size=3.0, n=1):
        for _ in range(n):
            jx = random.uniform(-0.3, 0.3)
            jy = random.uniform(0, 0.4)
            jz = random.uniform(-0.3, 0.3)
            self.p.append(
                Particle(x, y, z, vx + jx, vy + jy, vz + jz, life, life, *col, size)
            )

    def update(self, dt):
        alive = []
        for p in self.p:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.z += p.vz * dt
            p.vy -= 6 * dt
            p.life -= dt
            if p.life > 0:
                alive.append(p)
        self.p = alive

    def draw(self):
        if not self.p:
            return
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glPointSize(4.0)
        glBegin(GL_POINTS)
        for p in self.p:
            a = (p.life / p.max_life) ** 0.5
            glColor4f(p.r, p.g, p.b, a * 0.9)
            glVertex3f(p.x, p.y, p.z)
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_BLEND)
        glEnable(GL_LIGHTING)


@dataclass
class Building:
    x: float
    z: float
    w: float
    d: float
    h: float
    col_idx: int
    win_col_idx: int
    win_pattern: List


def gen_building(x: float, z: float) -> Building:
    w = random.uniform(3, 9)
    d = random.uniform(3, 9)
    h = random.uniform(8, 55)
    ci = random.randint(0, len(C_BUILDING) - 1)
    wci = random.randint(0, len(C_BUILDING_WIN) - 1)
    wins = []
    cols = random.randint(2, 4)
    rows = max(2, int(h / 4))
    for r in range(rows):
        for c in range(cols):
            if random.random() > 0.35:
                wx = (c + 0.25) * (w / cols)
                wy = (r + 0.3) * (h / rows)
                ww = (w / cols) * 0.45
                wh = (h / rows) * 0.4
                wins.append((wx, wy, ww, wh))
    return Building(x, z, w, d, h, ci, wci, wins)


def draw_building(b: Building, player_z: float):
    glDisable(GL_TEXTURE_2D)
    glPushMatrix()
    glTranslatef(b.x, 0, b.z)

    bc = C_BUILDING[b.col_idx]
    glColor3f(*bc)
    _draw_box(b.w, b.h, b.d)

    wc = C_BUILDING_WIN[b.win_col_idx]
    glColor3f(*wc)
    for wx, wy, ww, wh in b.win_pattern:
        glPushMatrix()
        glTranslatef(wx - b.w * 0.5 + ww * 0.5, wy, b.d * 0.5 + 0.01)
        glScalef(ww, wh, 0.01)
        _draw_box(1, 1, 1)
        glPopMatrix()

    glPopMatrix()
    glEnable(GL_TEXTURE_2D)


def _draw_box(w, h, d):
    hw = w / 2
    hh = h / 2
    hd = d / 2
    faces = [
        [(-hw, -hh, hd), (hw, -hh, hd), (hw, hh, hd), (-hw, hh, hd)],
        [(hw, -hh, -hd), (-hw, -hh, -hd), (-hw, hh, -hd), (hw, hh, -hd)],
        [(-hw, -hh, -hd), (-hw, -hh, hd), (-hw, hh, hd), (-hw, hh, -hd)],
        [(hw, -hh, hd), (hw, -hh, -hd), (hw, hh, -hd), (hw, hh, hd)],
        [(-hw, hh, hd), (hw, hh, hd), (hw, hh, -hd), (-hw, hh, -hd)],
    ]
    glBegin(GL_QUADS)
    for face in faces:
        for v in face:
            glVertex3f(*v)
    glEnd()


class Track:
    def __init__(self):
        self.offset = 0.0
        self.buildings_L: List[Building] = []
        self.buildings_R: List[Building] = []
        self._last_build_z = 0.0
        self._spawn_buildings(0.0, TRACK_SEGS * TRACK_SEG_LEN)

    def _spawn_buildings(self, z_start, z_end):
        z = z_start
        while z < z_end:
            gap = random.uniform(1, 4)
            bL = gen_building(-(TRACK_W / 2 + random.uniform(4, 14)), z)
            bR = gen_building((TRACK_W / 2 + random.uniform(4, 14)), z)
            self.buildings_L.append(bL)
            self.buildings_R.append(bR)
            z += bL.w + gap
        self._last_build_z = z

    def update(self, dz: float):
        self.offset += dz
        cull_z = self.offset - 20.0
        self.buildings_L = [b for b in self.buildings_L if b.z > cull_z]
        self.buildings_R = [b for b in self.buildings_R if b.z > cull_z]
        ahead = self.offset + VISIBLE_SEGS * TRACK_SEG_LEN
        if self._last_build_z < ahead:
            self._spawn_buildings(self._last_build_z, ahead + 60)

    def draw(self, player_z: float):
        self._draw_road(player_z)
        self._draw_sky()
        for b in self.buildings_L + self.buildings_R:
            draw_building(b, player_z)

    def _draw_road(self, pz: float):
        glDisable(GL_TEXTURE_2D)
        hw = TRACK_W / 2

        for i in range(VISIBLE_SEGS):
            z0 = pz + i * TRACK_SEG_LEN - TRACK_SEG_LEN
            z1 = pz + (i + 1) * TRACK_SEG_LEN - TRACK_SEG_LEN

            glColor3f(*C_ROAD)
            glBegin(GL_QUADS)
            glVertex3f(-hw, 0, z0)
            glVertex3f(hw, 0, z0)
            glVertex3f(hw, 0, z1)
            glVertex3f(-hw, 0, z1)
            glEnd()

            dash = TRACK_SEG_LEN * 0.45
            dz0 = z0
            dz1 = dz0 + dash
            for lane_i in range(1, LANE_COUNT):
                lx = -hw + lane_i * LANE_W
                glColor3f(*C_ROAD_LINE)
                glLineWidth(2.0)
                glBegin(GL_LINES)
                glVertex3f(lx, 0.02, dz0)
                glVertex3f(lx, 0.02, dz1)
                glEnd()

            for ex, col in [(-hw, C_ROAD_EDGE), (hw, C_ROAD_EDGE)]:
                glColor3f(*col)
                glLineWidth(3.0)
                glBegin(GL_LINES)
                glVertex3f(ex, 0.03, z0)
                glVertex3f(ex, 0.03, z1)
                glEnd()

            glColor3f(C_GRID[0], C_GRID[1], C_GRID[2])
            glLineWidth(1.0)
            glBegin(GL_LINES)
            glVertex3f(-hw, 0.01, z0)
            glVertex3f(hw, 0.01, z0)
            glEnd()

        for sx in [-hw - 0.3, hw + 0.3]:
            glColor3f(*C_ROAD_EDGE)
            glBegin(GL_QUADS)
            glVertex3f(sx - 0.2, 0, pz - TRACK_SEG_LEN)
            glVertex3f(sx + 0.2, 0, pz - TRACK_SEG_LEN)
            glVertex3f(sx + 0.2, 0.9, pz + VISIBLE_SEGS * TRACK_SEG_LEN)
            glVertex3f(sx - 0.2, 0.9, pz + VISIBLE_SEGS * TRACK_SEG_LEN)
            glEnd()

        glLineWidth(1.0)

    def _draw_sky(self):
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        dist = 300.0
        glBegin(GL_QUADS)
        glColor3f(*C_SKY_MID)
        glVertex3f(-dist, 0, dist)
        glColor3f(*C_SKY_MID)
        glVertex3f(dist, 0, dist)
        glColor3f(*C_SKY_TOP)
        glVertex3f(dist, dist, dist)
        glColor3f(*C_SKY_TOP)
        glVertex3f(-dist, dist, dist)

        glColor3f(*C_SKY_MID)
        glVertex3f(-dist, 0, -dist)
        glColor3f(*C_SKY_MID)
        glVertex3f(-dist, 0, dist)
        glColor3f(*C_SKY_TOP)
        glVertex3f(-dist, dist, dist)
        glColor3f(*C_SKY_TOP)
        glVertex3f(-dist, dist, -dist)

        glColor3f(*C_SKY_MID)
        glVertex3f(dist, 0, dist)
        glColor3f(*C_SKY_MID)
        glVertex3f(dist, 0, -dist)
        glColor3f(*C_SKY_TOP)
        glVertex3f(dist, dist, -dist)
        glColor3f(*C_SKY_TOP)
        glVertex3f(dist, dist, dist)
        glEnd()
        glEnable(GL_LIGHTING)


@dataclass
class Obstacle:
    lane: int
    z: float
    kind: str
    active: bool = True
    anim: float = 0.0
    health: int = 1

    @property
    def x(self):
        return lane_x(self.lane)

    def draw(self, t: float):
        if not self.active:
            return
        self.anim = t
        glDisable(GL_TEXTURE_2D)
        glPushMatrix()
        glTranslatef(self.x, 0, self.z)

        if self.kind == "wall":
            glColor3f(*C_OBSTACLE_A)
            _draw_box(LANE_W * 0.85, 2.0, 0.6)
            glColor3f(1.0, 0.5, 0.5)
            glPushMatrix()
            glTranslatef(0, 1.05, 0)
            _draw_box(LANE_W * 0.85, 0.12, 0.65)
            glPopMatrix()

        elif self.kind == "barrier":
            glColor3f(*C_OBSTACLE_B)
            _draw_box(LANE_W * 0.85, 0.9, 0.9)
            glColor3f(1.0, 0.8, 0.3)
            glPushMatrix()
            glTranslatef(0, 0.5, 0)
            _draw_box(LANE_W * 0.85, 0.1, 0.95)
            glPopMatrix()

        elif self.kind == "drone":
            bob = math.sin(t * 3.0) * 0.25
            glTranslatef(0, 2.5 + bob, 0)
            glColor3f(*C_DRONE)
            glPushMatrix()
            glScalef(1.2, 0.4, 1.2)
            _draw_box(1, 1, 1)
            glPopMatrix()
            rot = (t * 400) % 360
            for rx, rz in [(-0.8, 0), (0.8, 0), (0, -0.8), (0, 0.8)]:
                glPushMatrix()
                glTranslatef(rx, 0.25, rz)
                glRotatef(rot, 0, 1, 0)
                glColor3f(0.7, 0.1, 0.1)
                glScalef(0.55, 0.06, 0.1)
                _draw_box(1, 1, 1)
                glPopMatrix()
            glColor3f(1.0, 0.9, 0.0)
            glPushMatrix()
            glTranslatef(0, 0, 0.6)
            _draw_sphere(0.12, 8)
            glPopMatrix()

        elif self.kind == "spike":
            for sx in [-LANE_W * 0.25, 0, LANE_W * 0.25]:
                glPushMatrix()
                glTranslatef(sx, 0, 0)
                glColor3f(*C_OBSTACLE_A)
                _draw_pyramid(0.35, 1.2)
                glPopMatrix()

        glPopMatrix()
        glEnable(GL_TEXTURE_2D)

    def collision_box(self):
        hw = LANE_W * 0.42
        if self.kind == "wall":
            return self.x - hw, self.x + hw, 0, 2.05, self.z, 0.5
        elif self.kind == "barrier":
            return self.x - hw, self.x + hw, 0, 0.95, self.z, 0.6
        elif self.kind == "drone":
            return self.x - 0.7, self.x + 0.7, 2.0, 3.2, self.z, 0.6
        elif self.kind == "spike":
            return self.x - hw, self.x + hw, 0, 1.3, self.z, 0.7
        return self.x - hw, self.x + hw, 0, 2.0, self.z, 0.5


def _draw_sphere(r, slices=12):
    q = gluNewQuadric()
    gluSphere(q, r, slices, slices)
    gluDeleteQuadric(q)


def _draw_cylinder(r, h, slices=12):
    q = gluNewQuadric()
    gluCylinder(q, r, r, h, slices, 1)
    gluDeleteQuadric(q)


def _draw_pyramid(base, height):
    hb = base / 2
    glBegin(GL_TRIANGLES)
    apex = (0, height, 0)
    verts = [(-hb, 0, -hb), (hb, 0, -hb), (hb, 0, hb), (-hb, 0, hb)]
    for i in range(4):
        a = verts[i]
        b = verts[(i + 1) % 4]
        glVertex3f(*apex)
        glVertex3f(*a)
        glVertex3f(*b)
    glEnd()
    glBegin(GL_QUADS)
    for v in verts:
        glVertex3f(*v)
    glEnd()


@dataclass
class Pickup:
    lane: int
    z: float
    kind: str
    collected: bool = False
    anim: float = 0.0

    @property
    def x(self):
        return lane_x(self.lane)

    def draw(self, t: float):
        if self.collected:
            return
        bob = math.sin(t * 3.0 + self.lane) * 0.18
        spin = (t * 150) % 360

        glDisable(GL_TEXTURE_2D)
        glPushMatrix()
        glTranslatef(self.x, 1.2 + bob, self.z)
        glRotatef(spin, 0, 1, 0)

        if self.kind == "coin":
            glColor3f(*C_COIN)
            glScalef(1, 1, 0.15)
            _draw_sphere(0.28, 12)
            glColor3f(1.0, 0.7, 0.0)
            glScalef(0.6, 0.6, 1)
            _draw_sphere(0.28, 8)

        elif self.kind == "shield":
            glColor3f(*C_SHIELD)
            glBegin(GL_POLYGON)
            for i in range(6):
                a = i * math.pi / 3
                glVertex3f(math.cos(a) * 0.38, math.sin(a) * 0.38, 0)
            glEnd()
            glColor3f(0.8, 0.95, 1.0)
            glBegin(GL_LINE_LOOP)
            for i in range(6):
                a = i * math.pi / 3
                glVertex3f(math.cos(a) * 0.4, math.sin(a) * 0.4, 0)
            glEnd()

        elif self.kind == "magnet":
            glColor3f(*C_MAGNET)
            glPushMatrix()
            glTranslatef(-0.15, 0, 0)
            _draw_cylinder(0.10, 0.5, 8)
            glPopMatrix()
            glPushMatrix()
            glTranslatef(0.15, 0, 0)
            _draw_cylinder(0.10, 0.5, 8)
            glPopMatrix()
            glPushMatrix()
            glTranslatef(0, 0.25, 0)
            glRotatef(90, 0, 0, 1)
            _draw_cylinder(0.10, 0.30, 8)
            glPopMatrix()

        elif self.kind == "double":
            glColor3f(*C_DOUBLE)
            glPushMatrix()
            glTranslatef(-0.15, 0, 0)
            glScalef(0.7, 1.0, 0.7)
            _draw_sphere(0.28)
            glPopMatrix()
            glPushMatrix()
            glTranslatef(0.15, 0, 0)
            glScalef(0.7, 1.0, 0.7)
            _draw_sphere(0.28)
            glPopMatrix()

        glPopMatrix()
        glEnable(GL_TEXTURE_2D)


class Player:
    def __init__(self):
        self.lane = 1
        self.target_x = lane_x(1)
        self.x = self.target_x
        self.y = PLAYER_Y_GROUND
        self.z = 0.0

        self.jump_t = 0.0
        self.jumping = False
        self.sliding = False
        self.slide_t = 0.0

        self.alive = True
        self.shield = 0.0
        self.magnet = 0.0
        self.double_sc = 0.0
        self.invincible = 0.0

        self.score = 0.0
        self.coins = 0
        self.distance = 0.0
        self.multiplier = 1
        self.combo = 0
        self.run_time = 0.0

        self.trail: List[Tuple] = []
        self.trail_timer = 0.0

    def switch_lane(self, direction: int):
        new_lane = clamp(self.lane + direction, 0, LANE_COUNT - 1)
        if new_lane != self.lane:
            self.lane = new_lane
            self.target_x = lane_x(new_lane)

    def jump(self):
        if not self.jumping and not self.sliding:
            self.jumping = True
            self.jump_t = 0.0
            self.invincible = 0.1

    def slide(self):
        if not self.jumping:
            self.sliding = True
            self.slide_t = 0.0

    def update(self, dt: float, speed: float, particles: "Particles"):
        if not self.alive:
            return

        self.run_time += dt
        self.distance += speed * dt
        self.score += speed * dt * 0.1 * self.multiplier

        self.x = lerp(self.x, self.target_x, LANE_SWITCH_SPD * dt)

        if self.jumping:
            self.jump_t += dt / JUMP_DUR
            if self.jump_t >= 1.0:
                self.jump_t = 1.0
                self.jumping = False
            self.y = PLAYER_Y_JUMP * math.sin(self.jump_t * math.pi)
        else:
            self.y = PLAYER_Y_GROUND

        if self.sliding:
            self.slide_t += dt / SLIDE_DUR
            if self.slide_t >= 1.0:
                self.sliding = False

        for attr in ["shield", "magnet", "double_sc", "invincible"]:
            v = getattr(self, attr)
            if v > 0:
                setattr(self, attr, max(0.0, v - dt))
        if self.double_sc > 0:
            self.multiplier = 2
        else:
            self.multiplier = 1

        self.trail_timer -= dt
        if self.trail_timer <= 0:
            self.trail_timer = 0.04
            tc = C_SHIELD if self.shield > 0 else C_TRAIL
            particles.emit(
                self.x,
                self.y + 0.5,
                self.z,
                random.uniform(-0.3, 0.3),
                0.5,
                -speed * 0.3,
                0.35,
                tc,
                3.0,
                3,
            )

        if self.shield > 0:
            if random.random() < 0.3:
                a = random.uniform(0, 2 * math.pi)
                particles.emit(
                    self.x + math.cos(a) * 0.7,
                    self.y + 0.8 + math.sin(a) * 0.7,
                    self.z,
                    math.cos(a) * 1.5,
                    math.sin(a) * 1.5,
                    0,
                    0.2,
                    C_SHIELD,
                    4.0,
                )

    def collision_box(self):
        h = 0.7 if self.sliding else 1.7
        return (self.x - 0.45, self.x + 0.45, self.y, self.y + h)

    def draw(self, t: float):
        glDisable(GL_TEXTURE_2D)
        glPushMatrix()
        glTranslatef(self.x, self.y, self.z)

        scale_y = 0.55 if self.sliding else 1.0
        glScalef(1, scale_y, 1)

        if self.shield > 0:
            glColor4f(*C_SHIELD, 0.25)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE)
            _draw_sphere(1.1, 14)
            glDisable(GL_BLEND)

        leg_swing = math.sin(t * 10.0) * 25.0 * (0 if self.jumping else 1)
        for lx, phase in [(-0.22, 1), (0.22, -1)]:
            glPushMatrix()
            glTranslatef(lx, 0.4, 0)
            glRotatef(leg_swing * phase, 1, 0, 0)
            glColor3f(0.1, 0.5, 0.8)
            glScalef(0.18, 0.55, 0.18)
            _draw_box(1, 1, 1)
            glPopMatrix()

        glColor3f(*C_PLAYER)
        glPushMatrix()
        glTranslatef(0, 1.0, 0)
        glScalef(0.55, 0.65, 0.30)
        _draw_box(1, 1, 1)
        glPopMatrix()

        arm_swing = math.sin(t * 10.0) * 30.0 * (0 if self.jumping else 1)
        for ax, phase in [(-0.42, -1), (0.42, 1)]:
            glPushMatrix()
            glTranslatef(ax, 0.95, 0)
            glRotatef(arm_swing * phase, 1, 0, 0)
            glColor3f(0.12, 0.60, 0.95)
            glScalef(0.16, 0.50, 0.16)
            _draw_box(1, 1, 1)
            glPopMatrix()

        glColor3f(*C_PLAYER_GLOW)
        glPushMatrix()
        glTranslatef(0, 1.62, 0)
        glScalef(1, 1, 0.85)
        _draw_sphere(0.28, 12)
        glPopMatrix()

        glColor3f(0.8, 1.0, 1.0)
        glPushMatrix()
        glTranslatef(0, 1.62, 0.22)
        glScalef(0.5, 0.18, 0.2)
        _draw_box(1, 1, 1)
        glPopMatrix()

        glPopMatrix()
        glEnable(GL_TEXTURE_2D)


class HUD:
    def __init__(self):
        pygame.font.init()
        self.f_title = pygame.font.SysFont("couriernew", 36, bold=True)
        self.f_big = pygame.font.SysFont("couriernew", 28, bold=True)
        self.f_med = pygame.font.SysFont("couriernew", 20, bold=True)
        self.f_sm = pygame.font.SysFont("couriernew", 15)

    def _blit(self, text, font, color, x, y):
        surf = font.render(text, True, color)
        w, h = surf.get_size()
        data = pygame.image.tostring(surf, "RGBA", True)
        glRasterPos2f(x, SH - y - h)
        glDrawPixels(w, h, GL_RGBA, GL_UNSIGNED_BYTE, data)

    def _rect(self, x, y, w, h):
        glBegin(GL_QUADS)
        glVertex2f(x, y)
        glVertex2f(x + w, y)
        glVertex2f(x + w, y + h)
        glVertex2f(x, y + h)
        glEnd()

    def draw(self, player: Player, speed: float, t: float):
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, SW, 0, SH, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glColor4f(0, 0, 0, 0.5)
        self._rect(SW - 260, SH - 68, 250, 62)
        self._blit(f"{int(player.score):08d}", self.f_big, (20, 240, 215), SW - 255, SH - 36)
        self._blit("SCORE", self.f_sm, (80, 180, 170), SW - 255, SH - 58)

        self._blit(f"{int(player.distance)}m", self.f_med, (180, 180, 220), SW - 255, SH - 90)

        spd_pct = (speed - BASE_SPEED) / (MAX_SPEED - BASE_SPEED)
        glColor4f(0, 0, 0, 0.5)
        self._rect(14, SH - 34, 180, 22)
        glColor4f(0.1, 0.9, 0.7, 0.85)
        self._rect(16, SH - 32, int(176 * spd_pct), 18)
        glColor4f(0.1, 0.9, 0.7, 0.4)
        glBegin(GL_LINE_LOOP)
        glVertex2f(14, SH - 34)
        glVertex2f(194, SH - 34)
        glVertex2f(194, SH - 12)
        glVertex2f(14, SH - 12)
        glEnd()
        self._blit(f"SPD  {int(speed)}", self.f_sm, (20, 220, 200), 16, SH - 54)

        if player.multiplier > 1:
            pulse = abs(math.sin(t * 4)) * 0.5 + 0.5
            c = (int(255 * pulse), int(160 * pulse), 20)
            self._blit(f"x{player.multiplier} MULTIPLIER", self.f_med, c, SW // 2 - 80, SH - 38)

        self._blit(f"◆ {player.coins}", self.f_med, (255, 220, 40), 16, SH - 80)

        py = SH - 120
        if player.shield > 0:
            self._draw_powerup_bar("SHIELD", player.shield, 5.0, (20, 180, 255), py)
            py -= 28
        if player.magnet > 0:
            self._draw_powerup_bar("MAGNET", player.magnet, 5.0, (200, 60, 255), py)
            py -= 28
        if player.double_sc > 0:
            self._draw_powerup_bar("2x SCR", player.double_sc, 5.0, (255, 140, 20), py)

        cx, cy = SW // 2, SH // 2
        glColor4f(0.2, 0.9, 0.8, 0.5)
        self._rect(cx - 1, cy - 8, 2, 16)
        self._rect(cx - 8, cy - 1, 16, 2)

        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()

    def _draw_powerup_bar(self, label, val, max_val, color, y):
        pct = val / max_val
        glColor4f(0, 0, 0, 0.5)
        self._rect(14, y, 130, 20)
        glColor4f(*[c / 255 for c in color], 0.85)
        self._rect(16, y + 2, int(126 * pct), 16)
        self._blit(label, self.f_sm, color, 18, y + 2)

    def draw_gameover(self, player: Player):
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, SW, 0, SH, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(0, 0, 0.05, 0.82)
        self._rect(0, 0, SW, SH)
        self._blit("GAME  OVER", self.f_title, (240, 30, 80), SW // 2 - 150, SH // 2 - 80)
        self._blit(f"SCORE     {int(player.score):08d}", self.f_big, (20, 240, 215), SW // 2 - 160, SH // 2)
        self._blit(f"DISTANCE  {int(player.distance)}m", self.f_med, (180, 180, 255), SW // 2 - 160, SH // 2 + 40)
        self._blit(f"COINS     {player.coins}", self.f_med, (255, 220, 40), SW // 2 - 160, SH // 2 + 68)
        self._blit("[ R ] RESTART     [ ESC ] QUIT", self.f_med, (150, 150, 180), SW // 2 - 175, SH // 2 + 115)
        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()

    def draw_title(self, difficulty: int):
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, SW, 0, SH, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(0, 0, 0.06, 0.88)
        self._rect(0, 0, SW, SH)
        self._blit("NEON RUNNER", self.f_title, (20, 240, 215), SW // 2 - 145, SH // 2 - 130)
        self._blit("3D ENDLESS RUNNER", self.f_med, (200, 80, 255), SW // 2 - 120, SH // 2 - 80)

        diff_name = DIFFICULTY_PRESETS[difficulty]["name"]
        color = (255, 255, 100) if difficulty == 1 else (180, 220, 180) if difficulty == 2 else (255, 100, 100)
        self._blit(f"DIFFICULTY: {diff_name}", self.f_big, color, SW // 2 - 120, SH // 2 - 30)
        self._blit("[1] EASY   [2] MEDIUM   [3] HARD", self.f_med, (150, 200, 220), SW // 2 - 150, SH // 2 + 5)

        lines = [
            "← / → or  A / D  —  Switch Lane (A=right, D=left)",
            "SPACE / ↑        —  Jump (brief invincibility on takeoff)",
            "↓ / S            —  Slide",
            "P                —  Pause",
        ]
        for i, l in enumerate(lines):
            self._blit(l, self.f_sm, (160, 200, 220), SW // 2 - 155, SH // 2 + 45 + i * 22)
        self._blit("[ SPACE ] TO START", self.f_big, (240, 200, 20), SW // 2 - 165, SH // 2 + 135)
        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()

    def draw_pause(self):
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, SW, 0, SH, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(0, 0, 0.08, 0.72)
        self._rect(SW // 2 - 180, SH // 2 - 70, 360, 140)
        self._blit("PAUSED", self.f_title, (240, 180, 20), SW // 2 - 85, SH // 2 - 50)
        self._blit("[ P ] RESUME", self.f_med, (180, 220, 200), SW // 2 - 90, SH // 2 + 10)
        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()


class Spawner:
    def __init__(self):
        self.obstacles: List[Obstacle] = []
        self.pickups: List[Pickup] = []
        self._next_obstacle_z = 80.0
        self._next_pickup_z = 30.0
        self._coin_streak = 0
        self.gap_mult = 1.0
        self.pattern_weights = DIFFICULTY_PRESETS[2]["pattern_weights"]
        self.drone_factor = 1.0

    def set_difficulty(self, diff: int):
        preset = DIFFICULTY_PRESETS[diff]
        self.gap_mult = preset["obstacle_gap_mult"]
        self.pattern_weights = preset["pattern_weights"].copy()
        self.drone_factor = preset["drone_count_factor"]

    def update(self, player_z: float, speed: float, dt: float):
        look_ahead = player_z + VISIBLE_SEGS * TRACK_SEG_LEN

        effective_gap = OBSTACLE_GAP * self.gap_mult
        while self._next_obstacle_z < look_ahead:
            self._spawn_obstacle_group(self._next_obstacle_z, speed)
            self._next_obstacle_z += effective_gap + random.uniform(0, 14)

        while self._next_pickup_z < look_ahead:
            self._spawn_pickup(self._next_pickup_z)
            self._next_pickup_z += random.uniform(12, 28)

        cull = player_z - 10.0
        self.obstacles = [o for o in self.obstacles if o.z > cull]
        self.pickups = [p for p in self.pickups if p.z > cull]

    def _spawn_obstacle_group(self, z: float, speed: float):
        patterns = list(self.pattern_weights.keys())
        weights = list(self.pattern_weights.values())
        pattern = random.choices(patterns, weights)[0]
        speed_tier = (speed - BASE_SPEED) / (MAX_SPEED - BASE_SPEED)

        if pattern == "single":
            lane = random.randint(0, 2)
            kind = random.choice(["wall", "barrier", "spike"])
            self.obstacles.append(Obstacle(lane, z, kind))

        elif pattern == "double":
            start = random.randint(0, 1)
            kind = random.choice(["wall", "barrier"])
            self.obstacles.append(Obstacle(start, z, kind))
            self.obstacles.append(Obstacle(start + 1, z, kind))

        elif pattern == "zigzag":
            for i in range(3):
                lane = i % 3
                zoff = i * 8.0
                self.obstacles.append(Obstacle(lane, z + zoff, "barrier"))

        elif pattern == "flying":
            n = 1 + int(speed_tier * self.drone_factor * 2)
            lanes = random.sample(range(3), min(n, 3))
            for lane in lanes:
                self.obstacles.append(Obstacle(lane, z + random.uniform(0, 12), "drone"))

        elif pattern == "spikes" and speed_tier > 0.2:
            lane = random.randint(0, 2)
            self.obstacles.append(Obstacle(lane, z, "spike"))
            if speed_tier > 0.5 and random.random() < 0.5:
                other = (lane + 1) % 3
                self.obstacles.append(Obstacle(other, z + 10, "spike"))

    def _spawn_pickup(self, z: float):
        kind_weights = {"coin": 60, "shield": 12, "magnet": 12, "double": 16}
        kinds = list(kind_weights.keys())
        weights = list(kind_weights.values())
        kind = random.choices(kinds, weights)[0]

        if kind == "coin":
            lane = random.randint(0, 2)
            n = random.randint(3, 8)
            for i in range(n):
                self.pickups.append(Pickup(lane, z + i * 2.5, "coin"))
        else:
            lane = random.randint(0, 2)
            self.pickups.append(Pickup(lane, z, kind))


class Game:
    def __init__(self):
        self.state = "title"
        self.t = 0.0
        self.speed = BASE_SPEED
        self.difficulty = 2
        self._reset()

    def _reset(self):
        self.player = Player()
        self.track = Track()
        self.spawner = Spawner()
        self.spawner.set_difficulty(self.difficulty)
        self.particles = Particles()
        self.hud = HUD()
        preset = DIFFICULTY_PRESETS[self.difficulty]
        self.base_speed = BASE_SPEED * preset["speed_mult"]
        self.max_speed = MAX_SPEED * preset["max_speed_mult"]
        self.accel = SPEED_ACCEL * preset["accel_mult"]
        self.speed = self.base_speed
        self.cam_shake = 0.0

    def handle_event(self, ev):
        if self.state == "title":
            if ev.type == KEYDOWN:
                if ev.key == K_1:
                    self.difficulty = 1
                elif ev.key == K_2:
                    self.difficulty = 2
                elif ev.key == K_3:
                    self.difficulty = 3
                elif ev.key in (K_SPACE, K_RETURN):
                    self._reset()
                    self.state = "playing"

        elif self.state == "playing":
            if ev.type == KEYDOWN:
                if ev.key in (K_LEFT, K_a):
                    self.player.switch_lane(1)
                if ev.key in (K_RIGHT, K_d):
                    self.player.switch_lane(-1)
                if ev.key in (K_SPACE, K_UP):
                    self.player.jump()
                if ev.key in (K_DOWN, K_s):
                    self.player.slide()
                if ev.key == K_p:
                    self.state = "paused"

        elif self.state == "paused":
            if ev.type == KEYDOWN and ev.key == K_p:
                self.state = "playing"

        elif self.state == "dead":
            if ev.type == KEYDOWN and ev.key == K_r:
                self._reset()
                self.state = "playing"

    def update(self, dt: float):
        if self.state not in ("playing",):
            return
        self.t += dt

        self.speed = min(self.max_speed, self.speed + self.accel * dt * 60)

        dz = self.speed * dt
        self.player.z += dz
        self.track.update(dz)
        self.spawner.update(self.player.z, self.speed, dt)
        self.player.update(dt, self.speed, self.particles)
        self.particles.update(dt)

        if self.player.magnet > 0:
            for pk in self.spawner.pickups:
                if not pk.collected and pk.kind == "coin":
                    dx = self.player.x - pk.x
                    dz2 = self.player.z - pk.z
                    dist = math.hypot(dx, dz2)
                    if dist < 6.0:
                        pk.z += dz2 * 4 * dt
                        pk.lane = self.player.lane

        px1, px2, py1, py2 = self.player.collision_box()
        for pk in self.spawner.pickups:
            if pk.collected:
                continue
            if abs(pk.z - self.player.z) < 1.2 and pk.lane == self.player.lane:
                pk.collected = True
                if pk.kind == "coin":
                    self.player.coins += 1
                    self.player.score += 10 * self.player.multiplier
                    self.particles.emit(pk.x, 1.2, pk.z, 0, 3, 0, 0.4, C_COIN, 4, 12)
                elif pk.kind == "shield":
                    self.player.shield = 5.0
                    self.particles.emit(pk.x, 1.2, pk.z, 0, 2, 0, 0.6, C_SHIELD, 5, 20)
                elif pk.kind == "magnet":
                    self.player.magnet = 5.0
                    self.particles.emit(pk.x, 1.2, pk.z, 0, 2, 0, 0.5, C_MAGNET, 5, 15)
                elif pk.kind == "double":
                    self.player.double_sc = 5.0
                    self.particles.emit(pk.x, 1.2, pk.z, 0, 2, 0, 0.5, C_DOUBLE, 5, 15)

        if self.player.invincible <= 0:
            for ob in self.spawner.obstacles:
                if not ob.active:
                    continue
                ox1, ox2, oy1, oy2, oz, ohd = ob.collision_box()
                if abs(ob.z - self.player.z) > ohd + 0.6:
                    continue
                if px1 < ox2 and px2 > ox1 and py1 < oy2 and py2 > oy1:
                    if self.player.shield > 0:
                        self.player.shield = 0
                        ob.active = False
                        self.particles.emit(ob.x, oy2 * 0.5, ob.z, 0, 2, 0, 0.7, C_SHIELD, 6, 30)
                        self.cam_shake = 0.4
                    else:
                        self.player.alive = False
                        self.state = "dead"
                        self.cam_shake = 1.0
                        for _ in range(60):
                            a = random.uniform(0, 2 * math.pi)
                            s = random.uniform(1, 6)
                            self.particles.emit(
                                self.player.x,
                                self.player.y + 0.9,
                                self.player.z,
                                math.cos(a) * s,
                                random.uniform(2, 8),
                                math.sin(a) * s * 0.3,
                                random.uniform(0.5, 1.2),
                                C_OBSTACLE_A,
                                5,
                                1,
                            )
                        break

        self.cam_shake = max(0, self.cam_shake - dt * 3.0)

    def draw(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(FOV, SW / SH, NEAR, FAR)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        shake_x = math.sin(self.t * 40) * self.cam_shake * 0.25
        shake_y = math.cos(self.t * 33) * self.cam_shake * 0.15
        cam_x = self.player.x * 0.6 + shake_x
        cam_y = CAM_HEIGHT + self.player.y * 0.4 + shake_y
        cam_z = self.player.z - CAM_DIST
        look_x = self.player.x * 0.7
        look_y = self.player.y * 0.3 + 0.8
        look_z = self.player.z + CAM_LOOK_AHEAD
        gluLookAt(cam_x, cam_y, cam_z, look_x, look_y, look_z, 0, 1, 0)

        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_POSITION, [self.player.x, 6, self.player.z, 1])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.7, 0.8, 1.0, 1])
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.08, 0.05, 0.12, 1])
        glLightf(GL_LIGHT0, GL_QUADRATIC_ATTENUATION, 0.002)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [0.05, 0.03, 0.10, 1])

        glEnable(GL_FOG)
        glFogi(GL_FOG_MODE, GL_LINEAR)
        glFogfv(GL_FOG_COLOR, [0.12, 0.12, 0.25, 1])
        glFogf(GL_FOG_START, 40.0)
        glFogf(GL_FOG_END, VISIBLE_SEGS * TRACK_SEG_LEN * 0.9)

        self.track.draw(self.player.z)

        for ob in self.spawner.obstacles:
            ob.draw(self.t)

        for pk in self.spawner.pickups:
            pk.draw(self.t)

        self.player.draw(self.t)
        self.particles.draw()

        glDisable(GL_FOG)

        if self.state in ("playing", "dead"):
            self.hud.draw(self.player, self.speed, self.t)
        if self.state == "dead":
            self.hud.draw_gameover(self.player)
        if self.state == "title":
            self.hud.draw_title(self.difficulty)
        if self.state == "paused":
            self.hud.draw(self.player, self.speed, self.t)
            self.hud.draw_pause()


def main():
    pygame.init()
    pygame.display.set_caption("NEON RUNNER — 3D Endless Runner")
    pygame.display.set_mode((SW, SH), DOUBLEBUF | OPENGL)

    glEnable(GL_DEPTH_TEST)
    glDepthFunc(GL_LEQUAL)
    glShadeModel(GL_SMOOTH)
    glClearColor(0.12, 0.12, 0.25, 1.0)
    glHint(GL_PERSPECTIVE_CORRECTION_HINT, GL_NICEST)
    glEnable(GL_NORMALIZE)

    game = Game()
    clock = pygame.time.Clock()

    while True:
        dt = clock.tick(FPS) / 1000.0
        dt = min(dt, 0.05)

        events = pygame.event.get()
        for ev in events:
            if ev.type == QUIT:
                pygame.quit()
                sys.exit()
            if ev.type == KEYDOWN and ev.key == K_ESCAPE:
                pygame.quit()
                sys.exit()
            game.handle_event(ev)

        game.update(dt)
        game.draw()
        pygame.display.flip()


if __name__ == "__main__":
    main()