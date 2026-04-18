from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import re
from sqlalchemy import text

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///battleship.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

TEST_PASSWORD = "clemson-test-2026"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def check_test_auth():
    auth = request.headers.get("X-Test-Password") or request.headers.get("x-test-password", "")
    return auth == TEST_PASSWORD


def pick(data, *keys):
    if not isinstance(data, dict):
        return None
    for k in keys:
        if k in data:
            return data[k]
    return None


def parse_game_id(raw):
    if isinstance(raw, int):
        return raw
    if raw is None:
        return None
    s = str(raw).strip()
    if s.isdigit():
        return int(s)
    return None


def parse_player_id(raw):
    if isinstance(raw, int):
        return raw
    if raw is None:
        return None
    s = str(raw).strip()
    if s.isdigit():
        return int(s)
    return None


# -------------------------
# MODELS
# -------------------------

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    games_played = db.Column(db.Integer, default=0)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    total_shots = db.Column(db.Integer, default=0)
    total_hits = db.Column(db.Integer, default=0)


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    grid_size = db.Column(db.Integer, nullable=False)
    max_players = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="waiting_setup", nullable=False)
    current_turn_index = db.Column(db.Integer, default=0, nullable=False)


class GamePlayer(db.Model):
    game_id = db.Column(db.Integer, db.ForeignKey("game.id"), primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), primary_key=True)
    turn_order = db.Column(db.Integer, nullable=False)


class Ship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, nullable=False)
    player_id = db.Column(db.Integer, nullable=False)
    row = db.Column(db.Integer, nullable=False)
    col = db.Column(db.Integer, nullable=False)


class Move(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, nullable=False)
    player_id = db.Column(db.Integer, nullable=False)
    row = db.Column(db.Integer, nullable=False)
    col = db.Column(db.Integer, nullable=False)
    result = db.Column(db.String(10), nullable=False)
    timestamp = db.Column(db.String(50), nullable=False)


# -------------------------
# HEALTH
# -------------------------

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "api_version": "2.3"
    }), 200


# -------------------------
# SERVE FRONTEND
# -------------------------

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


# -------------------------
# RESET
# -------------------------

@app.route("/api/reset", methods=["POST"])
def reset():
    Move.query.delete()
    Ship.query.delete()
    GamePlayer.query.delete()
    Game.query.delete()
    Player.query.delete()

    try:
        db.session.execute(text("DELETE FROM sqlite_sequence WHERE name='game'"))
        db.session.execute(text("DELETE FROM sqlite_sequence WHERE name='player'"))
        db.session.execute(text("DELETE FROM sqlite_sequence WHERE name='ship'"))
        db.session.execute(text("DELETE FROM sqlite_sequence WHERE name='move'"))
    except Exception:
        pass

    db.session.commit()
    return jsonify({"status": "reset"}), 200


# -------------------------
# CREATE PLAYER
# -------------------------

@app.route("/api/players", methods=["POST"])
def create_player():
    data = request.get_json(silent=True)
    username = pick(data, "username", "playerName", "displayName")

    if username is None:
        return jsonify({"error": "bad_request"}), 400

    if not isinstance(username, str) or not username.strip():
        return jsonify({"error": "bad_request"}), 400

    if not USERNAME_RE.fullmatch(username):
        return jsonify({"error": "bad_request"}), 400

    existing = Player.query.filter_by(username=username).first()
    if existing:
        return jsonify({
            "player_id": existing.id,
            "playerId": existing.id,
            "username": existing.username,
            "displayName": existing.username,
            "error": "conflict"
        }), 409

    player = Player(username=username)
    db.session.add(player)
    db.session.commit()

    return jsonify({
        "player_id": player.id,
        "playerId": player.id,
        "username": player.username,
        "displayName": player.username
    }), 201


# -------------------------
# PLAYER STATS
# -------------------------

@app.route("/api/players/<player_id>/stats", methods=["GET"])
def get_stats(player_id):
    pid = parse_player_id(player_id)
    if pid is None:
        return jsonify({"error": "not_found"}), 404

    player = Player.query.get(pid)
    if not player:
        return jsonify({"error": "not_found"}), 404

    accuracy = 0.0
    if player.total_shots > 0:
        accuracy = player.total_hits / player.total_shots

    return jsonify({
        "games_played": player.games_played,
        "games": player.games_played,
        "wins": player.wins,
        "losses": player.losses,
        "total_shots": player.total_shots,
        "shots": player.total_shots,
        "total_hits": player.total_hits,
        "hits": player.total_hits,
        "accuracy": accuracy
    }), 200


# -------------------------
# CREATE GAME
# -------------------------

@app.route("/api/games", methods=["POST"])
def create_game():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "bad_request"}), 400

    creator_id = parse_player_id(pick(data, "creator_id", "creatorId"))
    grid_size = pick(data, "grid_size", "gridSize")
    max_players = pick(data, "max_players", "maxPlayers")

    if creator_id is None or grid_size is None or max_players is None:
        return jsonify({"error": "missing required fields"}), 400

    if not isinstance(grid_size, int) or grid_size < 5 or grid_size > 15:
        return jsonify({"error": "bad_request"}), 400

    if not isinstance(max_players, int) or max_players < 1:
        return jsonify({"error": "bad_request"}), 400

    creator = Player.query.get(creator_id)
    if not creator:
        return jsonify({"error": "invalid creator"}), 403

    game = Game(
        grid_size=grid_size,
        max_players=max_players,
        status="waiting_setup",
        current_turn_index=0
    )
    db.session.add(game)
    db.session.commit()

    db.session.add(GamePlayer(game_id=game.id, player_id=creator.id, turn_order=0))
    db.session.commit()

    return jsonify({
        "game_id": game.id,
        "grid_size": game.grid_size,
        "status": "waiting_setup"
    }), 201


# -------------------------
# LIST GAMES
# -------------------------

@app.route("/api/games", methods=["GET"])
def list_games():
    games = Game.query.all()
    result = []
    for g in games:
        player_count = GamePlayer.query.filter_by(game_id=g.id).count()
        result.append({
            "game_id": g.id,
            "grid_size": g.grid_size,
            "status": g.status,
            "max_players": g.max_players,
            "player_count": player_count
        })
    return jsonify(result), 200


# -------------------------
# JOIN GAME
# -------------------------

@app.route("/api/games/<game_id>/join", methods=["POST"])
def join_game(game_id):
    gid = parse_game_id(game_id)
    if gid is None:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json(silent=True)
    player_id = parse_player_id(pick(data, "player_id", "playerId", "playerld"))

    if player_id is None:
        return jsonify({"error": "bad_request"}), 400

    # Game must exist first
    game = Game.query.get(gid)
    if not game:
        return jsonify({"error": "not_found"}), 404

    # Player must exist
    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "not_found"}), 404

    # Game must still be open
    if game.status != "waiting_setup":
        return jsonify({"error": "game already started"}), 409

    # Player already in this game
    existing_gp = GamePlayer.query.filter_by(game_id=gid, player_id=player.id).first()
    if existing_gp:
        return jsonify({"error": "conflict"}), 409

    # Game full — 400
    count = GamePlayer.query.filter_by(game_id=gid).count()
    if count >= game.max_players:
        return jsonify({"error": "game full"}), 400

    db.session.add(GamePlayer(
        game_id=gid,
        player_id=player.id,
        turn_order=count
    ))
    db.session.commit()

    return jsonify({
        "status": "joined",
        "game_id": gid,
        "player_id": player.id
    }), 200


# -------------------------
# GET GAME
# -------------------------

@app.route("/api/games/<game_id>", methods=["GET"])
def get_game(game_id):
    gid = parse_game_id(game_id)
    if gid is None:
        return jsonify({"error": "not_found"}), 404

    game = Game.query.get(gid)
    if not game:
        return jsonify({"error": "not_found"}), 404

    active_players = GamePlayer.query.filter_by(game_id=gid).count()

    return jsonify({
        "game_id": game.id,
        "grid_size": game.grid_size,
        "status": game.status,
        "current_turn_index": game.current_turn_index,
        "active_players": active_players,
        "max_players": game.max_players
    }), 200


# -------------------------
# GET GAME PLAYERS
# -------------------------

@app.route("/api/games/<game_id>/players", methods=["GET"])
def get_game_players(game_id):
    gid = parse_game_id(game_id)
    if gid is None:
        return jsonify({"error": "not_found"}), 404

    game = Game.query.get(gid)
    if not game:
        return jsonify({"error": "not_found"}), 404

    gps = GamePlayer.query.filter_by(game_id=gid).order_by(GamePlayer.turn_order).all()
    result = []
    for gp in gps:
        p = Player.query.get(gp.player_id)
        result.append({
            "player_id": gp.player_id,
            "username": p.username if p else f"Player {gp.player_id}",
            "turn_order": gp.turn_order
        })
    return jsonify(result), 200


# -------------------------
# PLACE SHIPS
# -------------------------

@app.route("/api/games/<game_id>/place", methods=["POST"])
def place_ships(game_id):
    gid = parse_game_id(game_id)
    if gid is None:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json(silent=True)
    player_id = parse_player_id(pick(data, "player_id", "playerId", "playerld"))
    ship_list = pick(data, "ships")

    if player_id is None or ship_list is None:
        return jsonify({"error": "bad_request"}), 400

    game = Game.query.get(gid)
    if not game:
        return jsonify({"error": "not_found"}), 404

    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "invalid player"}), 403

    if GamePlayer.query.filter_by(game_id=gid, player_id=player_id).first() is None:
        return jsonify({"error": "player not in game"}), 403

    if Ship.query.filter_by(game_id=gid, player_id=player_id).first():
        return jsonify({"error": "conflict"}), 409

    if not isinstance(ship_list, list) or len(ship_list) != 3:
        return jsonify({"error": "bad_request"}), 400

    seen = set()
    for s in ship_list:
        row = pick(s, "row")
        col = pick(s, "col")

        if not isinstance(row, int) or not isinstance(col, int):
            return jsonify({"error": "bad_request"}), 400

        if row < 0 or row >= game.grid_size or col < 0 or col >= game.grid_size:
            return jsonify({"error": "bad_request"}), 400

        if (row, col) in seen:
            return jsonify({"error": "bad_request"}), 400

        seen.add((row, col))

    for row, col in seen:
        db.session.add(Ship(
            game_id=gid,
            player_id=player_id,
            row=row,
            col=col
        ))

    db.session.commit()

    placed = db.session.query(Ship.player_id) \
        .filter_by(game_id=gid) \
        .group_by(Ship.player_id) \
        .count()

    total = GamePlayer.query.filter_by(game_id=gid).count()

    if placed == total:
        game.status = "active"
        db.session.commit()

    return jsonify({"status": "placed"}), 200


# -------------------------
# FIRE
# -------------------------

@app.route("/api/games/<game_id>/fire", methods=["POST"])
def fire(game_id):
    gid = parse_game_id(game_id)
    if gid is None:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "bad_request"}), 400

    player_id = parse_player_id(pick(data, "player_id", "playerId", "playerld"))
    row = pick(data, "row")
    col = pick(data, "col")

    if player_id is None:
        return jsonify({"error": "bad_request"}), 400

    game = Game.query.get(gid)
    if not game:
        return jsonify({"error": "not_found"}), 404

    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "invalid player"}), 403

    if GamePlayer.query.filter_by(game_id=gid, player_id=player_id).first() is None:
        return jsonify({"error": "player not in game"}), 403

    # Finished — 400
    if game.status == "finished":
        return jsonify({"error": "game finished"}), 400

    # Not active — 400
    if game.status != "active":
        return jsonify({"error": "bad_request"}), 400

    if not isinstance(row, int) or not isinstance(col, int):
        return jsonify({"error": "bad_request"}), 400

    if row < 0 or row >= game.grid_size or col < 0 or col >= game.grid_size:
        return jsonify({"error": "bad_request"}), 400

    # Duplicate shot — 409 (must check before turn so both players get right error)
    existing_move = Move.query.filter_by(game_id=gid, row=row, col=col).first()
    if existing_move:
        return jsonify({"error": "conflict"}), 409

    # Check whose turn it is
    players_in_game = GamePlayer.query.filter_by(game_id=gid).order_by(GamePlayer.turn_order).all()
    current = players_in_game[game.current_turn_index].player_id
    if current != player_id:
        return jsonify({"error": "forbidden"}), 403

    hit_ship = Ship.query.filter_by(game_id=gid, row=row, col=col).first()
    result = "hit" if hit_ship else "miss"

    if hit_ship:
        db.session.delete(hit_ship)

    db.session.add(Move(
        game_id=gid,
        player_id=player_id,
        row=row,
        col=col,
        result=result,
        timestamp=datetime.utcnow().isoformat()
    ))

    player.total_shots += 1
    if result == "hit":
        player.total_hits += 1

    db.session.commit()

    living_opponents = []
    for gp in players_in_game:
        if gp.player_id == player_id:
            continue
        remaining = Ship.query.filter_by(game_id=gid, player_id=gp.player_id).count()
        if remaining > 0:
            living_opponents.append(gp.player_id)

    if len(living_opponents) == 0:
        game.status = "finished"
        for gp in players_in_game:
            p = Player.query.get(gp.player_id)
            p.games_played += 1
            if gp.player_id == player_id:
                p.wins += 1
            else:
                p.losses += 1
        db.session.commit()

        return jsonify({
            "result": result,
            "next_player_id": None,
            "game_status": "finished",
            "winner_id": player_id
        }), 200

    n = len(players_in_game)
    idx = game.current_turn_index
    for _ in range(n):
        idx = (idx + 1) % n
        pid = players_in_game[idx].player_id
        remaining = Ship.query.filter_by(game_id=gid, player_id=pid).count()
        if remaining > 0:
            break

    game.current_turn_index = idx
    db.session.commit()

    return jsonify({
        "result": result,
        "next_player_id": players_in_game[idx].player_id,
        "game_status": "active"
    }), 200


# -------------------------
# MOVES
# -------------------------

@app.route("/api/games/<game_id>/moves", methods=["GET"])
def get_moves(game_id):
    gid = parse_game_id(game_id)
    if gid is None:
        return jsonify({"error": "not_found"}), 404

    game = Game.query.get(gid)
    if not game:
        return jsonify({"error": "not_found"}), 404

    rows = Move.query.filter_by(game_id=gid).order_by(Move.id).all()
    payload = []
    for m in rows:
        payload.append({
            "game_id": gid,
            "player_id": m.player_id,
            "row": m.row,
            "col": m.col,
            "result": m.result,
            "timestamp": m.timestamp
        })

    return jsonify(payload), 200


# -------------------------
# TEST RESTART
# -------------------------

@app.route("/api/test/games/<game_id>/restart", methods=["POST"])
def test_restart(game_id):
    if not check_test_auth():
        return jsonify({"error": "forbidden"}), 403

    gid = parse_game_id(game_id)
    if gid is None:
        return jsonify({"error": "forbidden"}), 403

    game = Game.query.get(gid)
    if not game:
        return jsonify({"error": "not_found"}), 404

    Ship.query.filter_by(game_id=gid).delete()
    Move.query.filter_by(game_id=gid).delete()
    GamePlayer.query.filter_by(game_id=gid).delete()
    game.status = "waiting_setup"
    game.current_turn_index = 0
    db.session.commit()

    return jsonify({"status": "reset"}), 200


# -------------------------
# TEST PLACE SHIPS
# -------------------------

@app.route("/api/test/games/<game_id>/ships", methods=["POST"])
def test_place_ships(game_id):
    if not check_test_auth():
        return jsonify({"error": "forbidden"}), 403

    gid = parse_game_id(game_id)
    if gid is None:
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "forbidden"}), 403

    player_id = parse_player_id(pick(data, "player_id", "playerId", "playerld"))
    ship_list = pick(data, "ships")

    if player_id is None or ship_list is None:
        return jsonify({"error": "bad_request"}), 400

    game = Game.query.get(gid)
    if not game:
        return jsonify({"error": "not_found"}), 404

    if Player.query.get(player_id) is None:
        return jsonify({"error": "invalid player"}), 403

    if GamePlayer.query.filter_by(game_id=gid, player_id=player_id).first() is None:
        return jsonify({"error": "player not in game"}), 403

    Ship.query.filter_by(game_id=gid, player_id=player_id).delete()

    seen = set()
    for s in ship_list:
        row = pick(s, "row")
        col = pick(s, "col")

        if not isinstance(row, int) or not isinstance(col, int):
            return jsonify({"error": "bad_request"}), 400

        if row < 0 or row >= game.grid_size or col < 0 or col >= game.grid_size:
            return jsonify({"error": "bad_request"}), 400

        if (row, col) in seen:
            return jsonify({"error": "bad_request"}), 400

        seen.add((row, col))

    for row, col in seen:
        db.session.add(Ship(
            game_id=gid,
            player_id=player_id,
            row=row,
            col=col
        ))

    db.session.commit()

    placed = db.session.query(Ship.player_id).filter_by(game_id=gid).group_by(Ship.player_id).count()
    total = GamePlayer.query.filter_by(game_id=gid).count()
    if placed == total:
        game.status = "active"
        db.session.commit()

    return jsonify({"status": "ok"}), 200


# -------------------------
# TEST BOARD
# -------------------------

@app.route("/api/test/games/<game_id>/board/<player_id>", methods=["GET"])
def test_board(game_id, player_id):
    if not check_test_auth():
        return jsonify({"error": "forbidden"}), 403

    gid = parse_game_id(game_id)
    pid = parse_player_id(player_id)
    if gid is None or pid is None:
        return jsonify({"error": "forbidden"}), 403

    game = Game.query.get(gid)
    if not game:
        return jsonify({"error": "not_found"}), 404

    if Player.query.get(pid) is None:
        return jsonify({"error": "invalid player"}), 403

    ships_rows = Ship.query.filter_by(game_id=gid, player_id=pid).all()
    moves_rows = Move.query.filter_by(game_id=gid).order_by(Move.id).all()

    ships_payload = sorted([[s.row, s.col] for s in ships_rows])

    board = [["~" for _ in range(game.grid_size)] for _ in range(game.grid_size)]
    for s in ships_rows:
        board[s.row][s.col] = "O"

    for m in moves_rows:
        if 0 <= m.row < game.grid_size and 0 <= m.col < game.grid_size:
            board[m.row][m.col] = "X" if m.result == "hit" else "~"

    board_rows = [" ".join(r) for r in board]

    return jsonify({
        "game_id": gid,
        "player_id": pid,
        "ships": ships_payload,
        "board": board_rows,
        "moves": [
            {
                "player_id": m.player_id,
                "row": m.row,
                "col": m.col,
                "result": m.result,
                "timestamp": m.timestamp
            } for m in moves_rows
        ]
    }), 200


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
