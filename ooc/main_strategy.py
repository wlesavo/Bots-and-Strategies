import sys
import math
import numpy as np
import random
import timeit
from copy import deepcopy


class Mine:
    
    id         = 0
    mines      = {}     # mines storage
    potentials = {}     # potential mines
    
    def __init__(self, x, y):
        self.id = Mine.id
        Mine.id += 1
        self.x = x
        self.y = y
        Mine.mines.update({self.id : self})


class Enemy:
    
    sectors         = {} 
    enemies         = {} # pull of enemy states
    self_track      = {} # pull of self states from enemy point of view
    duplicates      = set() 
    self_duplicates = set()
    mass    = 0
    id      = 0

    def __init__(self, start, self_tracking):
        self.id     = Enemy.id
        Enemy.id    += 1
        self.x      = start[0]
        self.y      = start[1]
        self.sector = -1
        self.weight = 1
        self.mines  = {}
        self.modified    = False
        self.health_loss = 0
        self.grid = Game.grid.copy()
        self.grid[self.x, self.y] = 2
        self.self_tracking  = self_tracking
        self.zero_silence   = True
        if self.self_tracking:
            Enemy.self_track.update({self.id : self})
        else:
            Enemy.enemies.update({self.id : self})
        
    def make_action(action, self_tracking):
        # parsing input string and filtering candidates by moves, shoots,
        # mine triggers, sonars and handling silent moves
        
        for act in action.split("|"):
            b = act.split(" ") # ACTION PARAMETERS
            if b[0]   == "MOVE":
                Enemy.move(b[1], self_tracking)
            elif b[0] == "SURFACE":
                if self_tracking:
                    sector = Game.get_sector()
                else:
                    sector = int(b[1])
                Enemy.filter_surface(sector, self_tracking)
            elif b[0] == "TORPEDO":
                Enemy.shoot(int(b[1]), int(b[2]), self_tracking)
                Enemy.filter_shoot(int(b[1]), int(b[2]))
            elif b[0] == "SILENCE":
                if self_tracking:
                    # changing actual coordinates
                    d = Game.directions[b[1]]
                    dist = int(b[2])
                    Game.my_coors = (Game.my_coors[0] + dist * d[0], Game.my_coors[1] + dist * d[1])
                Enemy.silence(self_tracking)
            elif b[0] == "MINE":
                Enemy.plant_mine(self_tracking)
            elif b[0] == "TRIGGER":
                Enemy.filter_shoot(int(b[1]), int(b[2]))
                Enemy.filter_trigger(int(b[1]), int(b[2]), self_tracking)
            elif b[0] == "SONAR":
                if not self_tracking:
                    Enemy.filter_sonar(int(b[1]), False, not self_tracking)
        if self_tracking:
            Game.self_coors = np.zeros((17,17))
            for enemy in Enemy.self_track.values():
                enemy.get_sector()
                Game.self_coors[enemy.x + 1, enemy.y + 1] = 1
        else:
            Enemy.sectors = {}
            Enemy.mass    = 0
            min_weight_i  = min(Enemy.enemies.keys(), key = lambda x: Enemy.enemies[x].weight)
            min_weight    = Enemy.enemies[min_weight_i].weight
            for enemy in Enemy.enemies.values():
                sector       = enemy.get_sector()
                enemy.weight = enemy.weight/min_weight
                Enemy.mass  += enemy.weight
                count        = Enemy.sectors.get(sector, 0)
                Enemy.sectors.update({sector : count + 1})
    
    def move(direction, self_tracking):
        # filter candidates by moves
        d = Game.directions[direction]
        to_remove = []
        if self_tracking:
            Game.my_coors = (Game.my_coors[0] + d[0], Game.my_coors[1] + d[1])
            container = Enemy.self_track
        else:
            container = Enemy.enemies
        
        for i in container.keys():
            enemy = container[i]
            enemy.x += d[0]
            enemy.y += d[1]
            if 0 <= enemy.x < Game.width and 0 <= enemy.y < Game.height:
                if enemy.grid[enemy.x, enemy.y] == 2:
                    to_remove.append(i)
                else:
                    enemy.grid[enemy.x, enemy.y] = 2
            else:
                to_remove.append(i)
        for i in to_remove:
            #print("move", container[i].x, container[i].y, file = sys.stderr)
            container.pop(i)

    def silence(self_tracking):
        # handling silent moves
        # messy part of code due to *a lot* of unexpected behaviour
        # and the need to merge trajectories

        to_add = []
        if self_tracking:
            container = Enemy.self_track
        else:
            container = Enemy.enemies
            if Game.was_silenced:
                count_zer = 0
                count_non_zer = 0
                for e in Enemy.enemies.values():
                    if e.zero_silence:
                        count_zer += 1
                    else:
                        count_non_zer += 1
                if count_non_zer == 0 or count_zer == 1:
                    Game.silence_punish *= 1.5
            Game.was_silenced = True
            
        for i in container.keys():
            enemy = container[i]
            enemy.weight *= Game.silence_punish #punishing most popular 0 dist silence
            enemy.zero_silence = True
            for d in Game.directions.values():
                x = enemy.x
                y = enemy.y
                for r in range(1, 5):
                    x = x + d[0]
                    y = y + d[1]
                    if 0 <= x < Game.width and 0 <= y < Game.height:
                        if enemy.grid[x, y] == 0:
                            to_add.append([x, y, enemy, r])
                        else:
                            break
                    else:
                        break
        
        for i in to_add:
            a = list(filter(lambda a: (a.x == i[0] and a.y == i[1]), list(container.values())))
            if len(a) == 0:
                enemy = i[2]
                e = Enemy((i[0], i[1]), self_tracking)
                e.health_loss = enemy.health_loss
                e.zero_silence = False
                e.weight = enemy.weight/Game.silence_punish
                if i[3] == 4:
                    e.weight = e.weight * 0.4
                if i[3] == 3:
                    e.weight = e.weight * 0.7
                if i[3] == 1:
                    e.weight = e.weight * 1.5
                for mine_id in enemy.mines.keys():
                    e.mines.update({mine_id : enemy.mines[mine_id]})
                e.grid = enemy.grid.copy()
                for k in range(min(e.x, enemy.x), max(e.x, enemy.x) + 1):
                    for j in range(min(e.y, enemy.y), max(e.y, enemy.y) + 1):
                        e.grid[k, j] = 2
            else:
                old_enemy = container[a[0].id]
                enemy = i[2]
                old_enemy.modified = True
                if enemy.zero_silence:
                    old_enemy.zero_silence = True
                old_enemy.weight = max(enemy.weight/Game.silence_punish, old_enemy.weight)
                new_grid = enemy.grid.copy()
                for k in range(min(i[0], enemy.x), max(i[0], enemy.x) + 1):
                    for j in range(min(i[1], enemy.y), max(i[1], enemy.y) + 1):
                        new_grid[k, j] = 2
                old_enemy.grid = np.where(new_grid != old_enemy.grid, 0, new_grid)
                for mine_id in enemy.mines.keys():
                    mines = old_enemy.mines.get(mine_id, set())
                    #if len(mines) == 0:
                    #    print("mines old", old_enemy.mines, file = sys.stderr)
                    #    print("mines en", enemy.mines, file = sys.stderr)
                    mines.update(enemy.mines[mine_id])
                    old_enemy.mines.update({mine_id : mines})
                container.update({old_enemy.id: old_enemy})

    def shoot(x, y, self_tracking):
        # filter candidates by shoot range

        if self_tracking:
            container = Enemy.self_track
        else:
            container = Enemy.enemies
        a = Game.get_possible_shoots(x, y)
        to_remove = []
        for i in container.keys():
            enemy = container[i]
            if not a[enemy.x, enemy.y]:
                to_remove.append(i)
        for i in to_remove:
            #print("shoot", container[i].x, container[i].y, file = sys.stderr)
            container.pop(i)
            
    def get_sector(self):
        sx = self.x // 5
        sy = self.y // 5
        self.sector = sy * 3 + sx + 1
        return self.sector
    
    def filter_surface(i, self_tracking):
        # filter candidates by surface sector

        if self_tracking:
            container = Enemy.self_track
        else:
            container = Enemy.enemies
        i = i - 1
        x0 = (i % 3) * 5
        y0 = (i //3 ) * 5
        x1 = x0 + 5
        y1 = y0 + 5
        to_remove = []
        
        for i in container.keys():
            enemy = container[i]
            if x0 <= enemy.x < x1 and y0 <= enemy.y < y1:
                enemy.grid = Game.grid.copy()
                enemy.grid[enemy.x, enemy.y] = 2
            else:
                to_remove.append(i)
                
        for i in to_remove:
            #print("filter_surface", container[i].x, container[i].y, file = sys.stderr)
            container.pop(i) 
        for i in container.keys():
            container[i].health_loss += 1
                    
    def filter_sonar(sonar_id, found, self_tracking):
        # filter candidates by mine sonar

        if self_tracking:
            sector = Game.get_sector()
            found  = sector == sonar_id
            container = Enemy.self_track
        else:
            container = Enemy.enemies

        to_remove = []
        for i in container.keys():
            enemy = container[i]
            if found!=(sonar_id==enemy.sector):
                to_remove.append(i)
        for i in to_remove:
            #print("sonar", container[i].x, container[i].y, file = sys.stderr)
            container.pop(i)
        
    def filter_shoot(x, y):
        # count health_loss from shoot for all candidates

        for i in Enemy.enemies.keys():
            enemy = Enemy.enemies[i]
            if (abs(enemy.x - x) < 2 and abs(enemy.y - y) < 2):
                enemy.health_loss += 1
                if enemy.x == x and enemy.y == y:
                    enemy.health_loss += 1
        for i in Enemy.self_track.keys():
            enemy = Enemy.self_track[i]
            if (abs(enemy.x - x) < 2 and abs(enemy.y - y) < 2):
                enemy.health_loss += 1
                if enemy.x == x and enemy.y == y:
                    enemy.health_loss += 1
    
    def plant_mine(self_tracking):
        # add all possible mines from current place for every candidate

        mine_id = Mine.id
        Mine.id += 1
        if self_tracking:
            container = Enemy.self_track
        else:
            container = Enemy.enemies
        
        for i in container.keys():
            enemy = container[i]
            mines = set()
            for direction in Game.directions:
                d = Game.directions[direction]
                coor = (enemy.x + d[0], enemy.y + d[1])
                if 0 <= coor[0] < Game.width and 0 <= coor[1] < Game.height:
                    if Game.grid[enemy.x, enemy.y] == 0:
                        mines.add(coor)
            enemy.mines.update({mine_id : mines})
                
    def filter_trigger(x, y, self_tracking):
        # filter candidates by mine triggering
        # if they couldnt ever place a mine there

        to_remove = []
        if self_tracking:
            container  = Enemy.self_track
            duplicates = Enemy.self_duplicates
        else:
            container  = Enemy.enemies
            duplicates = Enemy.duplicates
            
        for i in container.keys():
            enemy = container[i]
            flag = True
            for mines in enemy.mines.values():
                if (x, y) in mines:
                    flag = False
                    break
            if flag:
                to_remove.append(i)
        
        for i in to_remove:
            print("trigger", container[i].x, container[i].y, file = sys.stderr)
            container.pop(i)
        
        for i in container.keys():
            enemy = container[i]
            count = 0
            id_to_remove = []
            for mine_id in enemy.mines.keys():
                mines = enemy.mines[mine_id]
                if (x, y) in mines:
                    count += 1
                    id_to_remove.append(mine_id)
            if count == 1:
                enemy.mines.pop(id_to_remove[0])
            else:
                for mine_id in id_to_remove:
                    #enemy.mines[mine_id] -= {(x, y)}
                    Game.duplicates += 1
                    duplicates.add((x, y))
        
        dups_to_remove = set()
        for dup in duplicates:
            if dup != (x, y):
                flag = True
                for i in container.keys():
                    enemy = container[i]
                    count = 0
                    id_to_remove = []
                    for mine_id in enemy.mines.keys():
                        mines = enemy.mines[mine_id]
                        if (x, y) in mines:
                            count += 1
                            id_to_remove.append(mine_id)
                    if count == 1:
                        enemy.mines.pop(id_to_remove[0])
                    elif count > 1:
                        flag = False
                if flag:
                    dups_to_remove.add(dup)
        for dup in dups_to_remove:
            duplicates -= {dup}

    def filter_damage(self_tracking):
        # filter candidates by a total health loss

        to_remove = []
        if self_tracking:
            opp_health_loss = Game.my_health_loss
            container = Enemy.self_track
        else:
            opp_health_loss = Game.opp_health_loss
            container = Enemy.enemies
                
        for i in container.keys():
            enemy = container[i]
            if enemy.health_loss!=opp_health_loss and (not enemy.modified):
                to_remove.append(i)
        for i in to_remove:
            container.pop(i)
        if not self_tracking:
            Enemy.mass = 0
            min_weight_i = min(Enemy.enemies.keys(), key = lambda x: Enemy.enemies[x].weight)
            min_weight = Enemy.enemies[min_weight_i].weight
            for e in Enemy.enemies.values():
                e.weight = e.weight/min_weight
                Enemy.mass += e.weight
    
    def get_self_dmg(x, y, direct, r):
        d = Game.directions[direct]
        x1 = x + r * d[0]
        y1 = y + r * d[1]
        self_dmg = Game.self_coors[x1:x1+3, y1:y1+3].sum()
        return self_dmg
    
    def evaluate_move(direction):
        # get the total candidates pool reduction 
        # due to a move in some direction

        d = Game.directions[direction]
        to_remove = []
        l = len(Enemy.self_track)
        count = 0
        for i in Enemy.self_track.keys():
            enemy = Enemy.self_track[i]
            x = enemy.x + d[0]
            y = enemy.y + d[1]
            if 0 <= x < Game.width and 0 <= y < Game.height:
                if enemy.grid[x, y] == 2:
                    count += 1               
            else:
                count += 1
        return l - count

    def evaluate_shoot(x, y, d = "N", r = 0):
        # get the total candidates pool reduction 
        # due to a shoot to some target
        l = len(Enemy.self_track)
        count = 0
        if l < 20:
            b = Enemy.get_self_dmg(x, y, d, r)
            a = Game.get_possible_shoots(x, y)
            for i in Enemy.self_track.keys():
                enemy = Enemy.self_track[i]
                if not a[enemy.x, enemy.y]:
                    count += 1
            return max(l - count - b, 0)
        else:
            return 4
    

class Game:

    directions = {"N":(0, -1), "S":(0, 1), "W":(-1, 0), "E":(1, 0)}
    cooldowns  = {"TORPEDO" : 3, "SONAR" : 4, "MINE" : 3, "SILENCE" : 6, "MOVE" : "0"}
    width  = -1 
    height = -1
    
    grid          = None
    my_map        = None
    distances     = None
    shoot_coor    = None
    last_sonar    = None
    trigger_coor  = None
    possible_path = None
    self_coors    = None
    cum_dang      = None
    path          = None

    was_sonared   = False
    was_shoot     = False
    was_triggered = False
    surfaced      = False
    was_silenced  = False
    danger        = False

    start           = 0
    turn_start      = 0
    opp_health_loss = 0
    my_health_loss  = 0
    max_time        = 0
    turn_time       = 0
    duplicates      = 0
    my_last_action  = "NA"
    my_coors        = (-1, -1)
    
    #tune parameters values intentionally left blank
    
    mine_estimation_threshold = #
    danger_limit              = #
    min_mines_count           = #
    shooting_threshold        = #
    mine_threshold            = #
    estimation_threshold      = #
    silence_punish            = #
    search_depth              = #
    search_time_limit         = #
    max_silence_range         = #
    surface_limit             = #
    gamma_path                = #
    
    def __init__(self):
        Game.width, Game.height, self.my_id = [int(i) for i in input().split()]
        Game.start = timeit.default_timer()
        self_coors = np.zeros((17,17))
        random.seed(516487 + self.my_id * 564682)
        self.x = 7
        self.y = 12
        self.my_prev_life = 6
        self.my_life      = 6
        self.opp_life     = 6
        self.torpedo_cooldown = 3
        self.sonar_cooldown   = 3
        self.silence_cooldown = 6 
        self.mine_cooldown    = 3
        Game.grid = np.zeros((Game.width, Game.height))
        for i in range(15):
            line = input()
            for j in range(Game.width):
                if line[j] == ".":
                    Game.grid[j, i] = 0
                else:
                    Game.grid[j, i] = 2
        for i in range(15):
            for j in range(15):
                if Game.grid[i, j] == 0:
                    Enemy((i, j), True)
                    Enemy((i, j), False)
        Enemy.mass = 0
        for e in Enemy.enemies.values():
            Enemy.mass += e.weight
        self.get_start()
        Game.my_map   = Game.grid.copy()
        Game.my_coors = (self.x, self.y)
        Game.my_map[Game.my_coors] = 2
        print(Game.my_coors)
    
    def update(self):
        # main update cycle, getting inputs, update cooldowns, filter stuff

        Game.path = None
        Game.turn_time += 1
        self.opp_prev_life     = self.opp_life
        self.my_prev_prev_life = self.my_prev_life
        self.my_prev_life      = self.my_life
        self.x, self.y, self.my_life, self.opp_life, self.torpedo_cooldown, self.sonar_cooldown, self.silence_cooldown, self.mine_cooldown = [int(i) for i in input().split()]
        Game.my_coors   = (self.x, self.y)
        Game.turn_start = timeit.default_timer()
        
        Game.cooldowns.update({"TORPEDO" : self.torpedo_cooldown, "SONAR" : self.sonar_cooldown, "MINE" : self.mine_cooldown, "SILENCE" : self.silence_cooldown})
        Game.opp_health_loss = self.opp_prev_life - self.opp_life
        Game.my_health_loss = self.my_prev_life - self.my_life
        
        if self.my_prev_life != self.my_life and not Game.surfaced:
            Game.danger = True

        Game.surfaced = False
        Game.my_map[self.x, self.y] = 2
        sonar_result = input()

        if Game.was_sonared:
            Game.was_sonared = False
            Enemy.filter_sonar(Game.last_sonar, sonar_result=="Y", False)
        
        opponent_orders = input()
        Enemy.make_action(opponent_orders, False)
        Enemy.filter_damage(False)
        Enemy.filter_damage(True)
        if len(Enemy.self_track.keys()) < 10:
            Game.danger = True
        
        for e in Enemy.enemies.values():
            e.health_loss = 0
            e.modified = False
        for e in Enemy.self_track.values():
            e.health_loss = 0
            e.modified = False

    def get_start(self):
        # random not *too* bad starting possition

        while True:
            x = random.randrange(1, Game.width-1)
            y = random.randrange(1, Game.height-1)
            #print(x, y, file=sys.stderr)
            if Game.grid[x, y]==0:
                for i in Game.directions.values():
                    if Game.grid[x+i[0], y+i[1]] == 2:
                        break
                else:
                    break
        self.x=x
        self.y=y
    
    def turn(self):
        # main cycle
        self.update()
        finish = self.get_finishing_blow()
        if not (finish is None):
            print(finish+"|MSG FATALITY")
            return
        cum_time = timeit.default_timer()
        Game.cum_dang = self.cumulative_danger()
        out = self.get_action()
        if Game.danger:
            if Game.cooldowns["SILENCE"] == 0:
                if Game.cooldowns["MINE"] <= 0 or self.my_life < 4:
                    s = self.get_silence()
                    if not (s is None):
                        Game.danger = False
                        Game.cooldowns["SILENCE"] == 6
                        out += "|SILENCE " + s[0] + " " + str(s[1])
        if Game.cooldowns["MINE"] <= 0:
            t = self.plant_mine()
            if not (t is None):
                out = out + "|MINE " + str(t[0])
                Game.cooldowns["MINE"] = 3
        
        Game.my_last_action = out
        Enemy.make_action(out, True)
        Game.max_time = max(Game.max_time, int((timeit.default_timer() - Game.turn_start)*1000))

        out  += "|MSG " + "e" + str(len(Enemy.enemies)) + " s" + str(len(Enemy.self_track)) + " " + str(Game.max_time)
        print(out)
    
    def get_action(self):
        # a lot of "if" with some hard prioritizing of actions. 
        # deffinetly not the best way to do this but 
        # it didn't seem to be that important to try to find a good eval here.
        
        t       = None # torpedo action
        m       = None # mine action
        t_out   = ""
        m_out   = ""
        t2_out  = ""
        m2_out  = ""
        out     = ""
        t_dam   = None
        m_dam   = None
        m_self_dam = None
        
        if Game.cooldowns["TORPEDO"] == 0:
            if len(Enemy.enemies)<Game.estimation_threshold:
                t = self.get_torpedo_target("N", 0)
                if not (t is None):
                    Game.cooldowns["TORPEDO"] = 3
                    t_out = "|TORPEDO " + str(t[0]) + " " + str(t[1])
                    t_dam = t[2]
                    Game.danger = True
        if len(Mine.mines) > 0:
            if len(Enemy.enemies)<Game.estimation_threshold:
                m = self.get_mine_to_trigger()
                if (not m is None):
                    m_out = m_out + "|TRIGGER " + str(m[0]) + " " + str(m[1])
                    m_dam = m[2]
                    m_self_dam = m[3]
        move = self.get_movement("")
        move_dir = move.split()[1]
        if Game.cooldowns["TORPEDO"] == 0:          
            if len(Enemy.enemies) < Game.estimation_threshold:
                t = self.get_torpedo_target(move_dir, 1)
                if not (t is None):
                    Game.danger = True
                    t2_out = "|TORPEDO " + str(t[0]) + " " + str(t[1])
        if len(Mine.mines) > 0:
            if len(Enemy.enemies) < Game.estimation_threshold:
                m = self.get_mine_to_trigger(d = move_dir, r = 1)
                if not (m is None):
                    if m_dam is None:
                        m2_out = "|TRIGGER " + str(m[0]) + " " + str(m[1])
                    elif m_dam < m[2]:
                        m2_out = "|TRIGGER " + str(m[0]) + " " + str(m[1])
                    elif m_dam == m[2]:
                        if m_self_dam > m[3]:
                            m2_out = "|TRIGGER " + str(m[0]) + " " + str(m[1])
        
        if len(t_out) > 0 or (len(t2_out) > 0 and Game.cooldowns["TORPEDO"] == 1):
            Game.cooldowns["TORPEDO"] = 3

        w = self.get_weapon_to_charge()
        out = move + " " + w
        if t2_out > t_out:
            out = out + t2_out
        else:
            out = t_out + out
        if len(m2_out) > 0:
            out = out + m2_out
        else:
            out = m_out + out
        if Game.cooldowns["SONAR"] == 0:
            t = self.get_sonar_id()
            if (not t is None):
                out = out + "|SONAR " + str(t)
                Game.was_sonared = True
                Game.last_sonar = t
                Game.danger = True
        return out
    
    def get_weapon_to_charge(self):
        # hardcoded order of charging weapons

        for cd in Game.cooldowns.keys():
            if cd!="MINE" and cd!="SONAR":
                if Game.cooldowns[cd] == 1:
                    Game.cooldowns[cd] -= 1
                    return cd
        if Game.cooldowns["MINE"] > 0 and len(Mine.mines) <= 1:
            Game.cooldowns["MINE"] -= 1
            return "MINE"
        elif Game.cooldowns["TORPEDO"] > 0:
            Game.cooldowns["TORPEDO"] -= 1
            return "TORPEDO"
        elif Game.cooldowns["SILENCE"] > 0:
            Game.cooldowns["SILENCE"] -= 1
            return "SILENCE"
        elif Game.cooldowns["MINE"] > 0 and len(Mine.mines)<=Game.min_mines_count:
            Game.cooldowns["MINE"] -= 1
            return "MINE"
        if Game.cooldowns["MINE"] <= 0:
            Game.cooldowns["SONAR"] -= 1
            return "SONAR"
        Game.cooldowns["MINE"] -= 1
        return "MINE"
    
    def get_torpedo_target(self, d, r):
        # some numpy to estimate best shooting target and 
        # if it is even worth shooting

        gamma = 0.9
        distances = Game.dist_fill(self.x, self.y, Game.grid, gamma)
        c = gamma**4
        a = np.logical_and(distances > c, distances < 1.5)
        # no self shooting
        a[self.x-1, self.y-1]                   = False
        a[self.x:self.x+2, self.y-1:self.y+2]   = False
        a[self.x-1:self.x+2, self.y:self.y+2]   = False
        a[self.x-1:self.x+2, self.y-1:self.y+2] = False
        m = 0
        out = None
        targets = []
        for i in range(Game.width):
            for j in range(Game.height):
                count = 0
                if a[i, j]:
                    for enemy in Enemy.enemies.values():
                        if (abs(enemy.x-i) < 2 and abs(enemy.y-j) < 2):
                            count += enemy.weight
                            if enemy.x == i and enemy.y == j:
                                count += enemy.weight
                    if count > m:
                        m = count
                        targets = [(i, j)]
                    elif count == m:
                        targets.append((i, j))
        if m/Enemy.mass > Game.shooting_threshold:
            if Game.my_health_loss == 0:
                max_ev = -1
                for en in targets:
                    ev = Enemy.evaluate_shoot(en[0], en[1], d, r)
                    if ev > max_ev:
                        max_ev = ev
                        b = en
                return (b[0], b[1], m/Enemy.mass)
            else:
                min_ev = 40
                for en in targets:
                    ev = Enemy.get_self_dmg(en[0], en[1], d, r)
                    if ev < min_ev:
                        min_ev = ev
                        b = en
                return (b[0], b[1], m/Enemy.mass)
        else:
            return None
    
    def get_possible_shoots(x, y):
        # get possible targets

        gamma = 0.9
        distances = Game.dist_fill(x, y, Game.grid, gamma)
        c = gamma**4
        return np.logical_and(distances > c, distances < 1.5)
       
    def get_mine_to_trigger(self, d = "N", r = 0):
        # estimate best trigger target and 
        # if it is worth triggering

        max_count = 0
        out = []
        for mine in Mine.mines.values():
            count = 0
            if abs(self.x-mine.x) > 1 or abs(self.y-mine.y) > 1:
                for enemy in Enemy.enemies.values():
                    if abs(enemy.x-mine.x) < 2 and abs(enemy.y-mine.y) < 2:
                        count += enemy.weight
                    if enemy.x == mine.x and enemy.y == mine.y:
                        count += enemy.weight
                if count > max_count:
                    max_count = count
                    out = [mine]
                elif count == max_count:
                    max_count = count
                    out.append(mine)
        if len(out) == 0:
            return None
        else:
            min_self_dmg = 10
            i = None
            for mine in out:
                dmg = Enemy.get_self_dmg(mine.x, mine.y, d, r)
                if dmg<min_self_dmg:
                    min_self_dmg = dmg
                    i = mine.id
            if i is None:
                return None
            b = Mine.mines[i]
            if max_count/Enemy.mass > Game.mine_threshold:
                b = Mine.mines.pop(i)
                Mine.potentials.pop(i)
                print(b.id, b.x, b.y, file=sys.stderr)
                return (b.x, b.y, max_count/Enemy.mass, min_self_dmg)
            else:
                return None

    def plant_mine(self):
        # plant action

        max_len = Game.cooldowns["TORPEDO"] + Game.cooldowns["SILENCE"] + 1
        path = [(self.x, self.y)]
        out = self.get_self_cum_danger(path, max_len)
        if not (out is None):
            d = Game.directions[out[0]]
            coor = (self.x + d[0], self.y + d[1])
            m = Mine(coor[0], coor[1])
            Mine.potentials.update({m.id : (self.x, self.y)})
            return out[0]
        return None
    
    def get_movement(self, last_action):
        # code is intentionally deleted as an important part of bot

        pass

    def get_silence(self):
        # code is intentionally deleted as an important part of bot

        pass

    def get_path(x, y, grid_in, danger, control):
        # main MC search loop for a path to follow

        def get_random_path(coor, cum_dang, l, max_c):
            # recursive path filling

            if l > Game.search_depth:
                return (cum_dang, l, max_c)
            temp = []
            dang = danger[coor[0], coor[1]]
            cum_dang += dang*(gamma**l)
            grid[coor[0], coor[1]] = 2
            path.append(coor)
            if control[coor[0], coor[1]]*(gamma**l) > max(5, max_c):
                max_c = control[coor[0], coor[1]]*(gamma**l)
            for d in Game.directions.values():
                c = (coor[0] + d[0], coor[1] + d[1])
                if 0 <= c[0] < Game.width and 0 <= c[1] < Game.height:
                    if grid[c[0], c[1]] == 0:
                        temp.append(c)            
            if len(temp) > 0:
                t = random.choice(temp)
                return get_random_path(t, cum_dang, l+1, max_c)
            else:
                return (cum_dang+1, l, max_c)
        
        gamma = Game.gamma_path
        out = []
        max_dam = 999
        st = timeit.default_timer()
        i = 0
        l_max = 0
        control_max = -1

        while True:
            i += 1
            path = []
            grid = grid_in.copy()
            rand_p = get_random_path((x, y), 0, 0, 0)
            # greedy path selection prioritizing by path length
            if rand_p[1] > l_max:
                l_max = rand_p[1]
                max_dam = rand_p[0]
                out = deepcopy(path)
                control_max = rand_p[2]
            elif rand_p[1] == l_max:
                if rand_p[0] < max_dam:
                    max_dam = rand_p[0]
                    out = deepcopy(path)
                    control_max = rand_p[2]
                elif rand_p[0] == max_dam:
                    if rand_p[2] > control_max:
                        control_max = rand_p[2]
                        out = deepcopy(path)
            if timeit.default_timer() - st > Game.search_time_limit:
                break
        a = x
        b = y
        out_string = []
        for p in out:
            for direct in Game.directions.keys():
                d = Game.directions[direct]
                if a + d[0] == p[0] and b+d[1] == p[1]:
                    out_string.append(direct)
                    a += d[0]
                    b += d[1]
                    break
        return (max_dam, l_max, out_string, out, control_max)
    
    def dist_fill(x, y, grid, gamma):
        # simple recursive bfs with gradient filling of a map
        
        def get_gradient(coors):
            temp = []
            for coor in coors:
                p = distances[coor[0], coor[1]]
                for d in Game.directions.values():
                    c = (coor[0] + d[0], coor[1] + d[1])
                    if 0 <= c[0] < Game.width and 0 <= c[1] < Game.height:
                        if distances[c[0], c[1]] < p * gamma:
                            distances[c[0], c[1]] = p * gamma
                            temp.append(c)
            if len(temp) > 0:
                get_gradient(temp)
            else:
                return
        distances = grid.copy()
        distances[x, y] = 1
        get_gradient([(x, y)])
        return distances

    def get_control_map(self):
        # somewhat successful attempt to implement 
        # voronoi diagram technique for estimation of
        # territories controled by opponent or myself

        def fill(coors, out):
            temp = []
            for coor in coors:
                out.append(coor)
                for d in Game.directions.values():
                    c = (coor[0] + d[0], coor[1] + d[1])
                    if 0 <= c[0] < Game.width and 0 <= c[1] < Game.height:
                        if free[c[0], c[1]] == 1 and checked[c[0], c[1]] == 0:
                            checked[c[0], c[1]] = 1
                            temp.append(c)
            if len(temp) > 0:
                return fill(temp, out)
            else:
                return out
        danger = Game.cum_dang > 0.4
        claimed = np.zeros((17,17))
        for mine in Mine.mines.values():
            claimed[mine.x:mine.x+3, mine.y:mine.y+3] = 1
        claimed = claimed[1:16, 1:16]
        free = danger + claimed + Game.my_map
        free = free == 0
        checked = np.zeros((15, 15))
        clusters = free.copy()
        k = 0
        for i in range(15):
            for j in range(15):
                if free[i, j] == 1:
                    if checked[i, j] == 0:
                        a = fill([(i, j)], [])
                        l = len(a)
                        for c in a:
                            clusters[c[0], c[1]] = l
        return clusters

    def cumulative_danger(self):
        # plotting a danger map from enemy possible mines

        a = np.zeros((17, 17))
        d = {}
        if len(Enemy.enemies)<Game.mine_estimation_threshold:
            for enemy in Enemy.enemies.values():
                for mines in enemy.mines.values():
                    l = len(mines)
                    dmg = enemy.weight/l
                    for mine in mines:
                        if not (mine in Enemy.duplicates):
                            dm = d.get(mine, 0)
                            d.update({mine:dm+dmg})
            for mine in d.keys():
                a[mine[0]:mine[0]+3, mine[1]:mine[1]+3] += d[mine]
                a[mine[0]+1, mine[1]+1] += d[mine]
            a = a[1:16, 1:16]/Enemy.mass
        else:
            a = a[1:16, 1:16]
        return a
    
    def get_self_cum_danger(self, path, max_len):
        # cummulative danger accross the full path 

        def score(arr, c):
            # count edges by shift
            arr[c[0]:c[0]+3, c[1]:c[1]+3] += 1
            b0 = arr[1:16, 1:16]
            count3 = np.count_nonzero(b0+Game.grid)
            b1 = np.roll(b0, 1, axis=0)
            b2 = np.roll(b0, 1, axis=1)
            b0 = b0[1:15, 1:15]
            b1 = b1[1:15, 1:15]
            b2 = b2[1:15, 1:15]
            count1 = abs(b0-b1)
            count2 = abs(b0-b2)
            summ = count1.sum() + count2.sum() - count3
            return summ
            
        max_len=min(len(path), max_len)
        a = np.zeros((17, 17))
        mines = set()
        for mine in Mine.mines.values():
            a[mine.x:mine.x+3, mine.y:mine.y+3] += 1
            mines.add((mine.x, mine.y))
        path_dang = {}
        for i in range(max_len):
            c = path[i]
            dang = {}
            for direct in Game.directions.keys():
                d = Game.directions[direct]
                coor = (c[0] + d[0], c[1] + d[1])
                if 0 < coor[0] < Game.width-1 and 0 < coor[1] < Game.height-1:
                    if Game.grid[coor[0], coor[1]] == 0:
                        if not coor in mines:
                            my_arr = a.copy()
                            sc = score(my_arr, coor)
                            dang.update({direct: sc})
            if len(dang)>0:
                min_d = min(dang.keys(), key = lambda x: dang[x])
                path_dang.update({i : (min_d, dang[min_d])})
            
        print("path_dang", path_dang, file = sys.stderr)            
        if len(path_dang)>0:
            c = path[0]
            d = Game.directions[path_dang[0][0]]
            coor = (c[0] + d[0], c[1] + d[1])
            count = 0
            for mine in mines:
                if abs(mine[0]-coor[0]) < 2 and abs(mine[1]-coor[1]) < 2:
                    count+=1
            if count > 1:
                return None
            return path_dang[0]
        else:
            return None
    
    def get_sector():
        # current sector

        sx = Game.my_coors[0] // 5
        sy = Game.my_coors[1] // 5
        return sy * 3 + sx + 1
    
    def get_sonar_id(self):
        if len(Enemy.sectors) > 1 and len(Enemy.enemies) > 10:
            return max(Enemy.sectors.keys(), key=lambda x: Enemy.sectors[x])
        else:
            return None

    def get_finishing_blow(self):
        # Messy and experimental part of code due to a lot of unpredictable edge cases.
        # This part remained untouched once it finally worked.
        # It had been rewrited a couple of times before that,
        # so i didnt have a courage to refactor this once again.
        # Main part of the function is also deprecated to make this part of code not runnable.

        def get_true_targets():
            e = list(Enemy.enemies.values())[0]
            targets = []
            x = e.x
            y = e.y
            for i in (-1, 0, 1):
                for j in (-1, 0, 1):
                    count = 0
                    for enemy in Enemy.enemies.values():
                        if (abs(enemy.x-(x+i)) < 2 and abs(enemy.y-(y+j)) < 2):
                            count+=1
                    if count == len(Enemy.enemies):
                        if 0 <= x+i < 15 and  0 <= y+j < 15:
                            targets.append((x+i, y+j))
            return targets
        
        def get_mines_to_trigger(targets):
            out = []
            for mine in Mine.mines.values():
                if (mine.x, mine.y) in targets:   
                    out.append(mine)
            return out
            
        def check_dir(grid, check, range1, range2):
            x = self.x
            y = self.y
            out = []
            for direct1 in Game.directions.keys():
                d1 = Game.directions[direct1]
                for r1 in range1:
                    x1 = x + r1*d1[0]
                    y1 = y + r1*d1[1]
                    if 0 <= x1 < Game.width and 0 <= y1 < Game.height:
                        if grid[x1, y1] == 0:
                            for direct2 in Game.directions.keys():
                                if direct1 != direct2:
                                    d2 = Game.directions[direct2]
                                    for r2 in range2:
                                        x2 = x1 + r2*d2[0]
                                        y2 = y1 + r2*d2[1]
                                        if 0 <= x2 < Game.width and 0 <= y2 < Game.height:
                                            if grid[x2, y2] == 0:
                                                if check[x2, y2]:
                                                    out.append((direct1, r1, direct2, r2, x2, y2))
                                            else:
                                                break
                                        else:
                                            break
                        else:
                            break            
                    else:
                        break
            return out          
                         
        def get_target(acts, life, targets):
            for a in acts:
                x = a[4]
                y = a[5]
                gamma = 0.9
                distances = Game.dist_fill(x, y, Game.grid, gamma)
                c = gamma**4
                check = np.logical_and(distances > c, distances < 1.5)
                for t in targets:
                    if check[t[0],t[1]]:
                        s_dmg = 0
                        if (abs(t[0]-x) < 2 and abs(t[1]-y) < 2):
                            s_dmg+=1
                            if t[0] == x and t[1] == y:
                                s_dmg += 1
                        if s_dmg < life:
                            return (a, t)
            return None
                     
        def get_coor(grid, life, shooting_range, targets):
            x = self.x
            y = self.y
            if Game.cooldowns["TORPEDO"] < 2 and Game.cooldowns["SILENCE"] == 0:
                #move second
                r1 = (0, 1, 2, 3, 4)
                r2 = [1]
                acts = check_dir(grid, shooting_range, r1, r2)
                targ = None
                if len(acts) > 0:
                    targ = get_target(acts, life, targets)
                if not (targ is None):
                    act = targ[0]
                    t = targ[1]
                    s = "|SILENCE " + act[0] + " " + str(act[1]) + "|MOVE " + act[2] + " TORPEDO" + "|TORPEDO " + str(t[0])+ " "+ str(t[1])
                    return (s, (act[4], act[5]))
            if Game.cooldowns["TORPEDO"] == 0 and Game.cooldowns["SILENCE"] < 2:
                r1 = [1]
                r2 = (0, 1, 2, 3, 4)
                acts = check_dir(grid, shooting_range, r1, r2)
                targ = None
                if len(acts) > 0:
                    targ = get_target(acts, life, targets)
                    
                if not (targ is None):
                    act = targ[0]
                    t = targ[1]
                    s = "|MOVE " + act[0] + " SILENCE" + "|SILENCE " + act[2] + " " + str(act[3]) + "|TORPEDO " + str(t[0])+ " "+ str(t[1])
                    return (s, (act[4], act[5]))
            if Game.cooldowns["TORPEDO"] < 2:
                #move first
                r1 = [1]
                r2 = [0]
                acts = check_dir(grid, shooting_range, r1, r2)
                targ = None
                if len(acts) > 0:
                    #print("acts", acts, file = sys.stderr, flush = True)
                    targ = get_target(acts, life, targets)
                if not (targ is None):
                    act = targ[0]
                    t = targ[1]
                    s = "|MOVE " + act[0] + " TORPEDO" + "|TORPEDO " + str(t[0]) + " " + str(t[1])
                    return (s, (act[4], act[5]))
            return None
        
        # here should be the main implementation of fatality

        return None
    
g = Game()
while True:
    g.turn()
    
    
