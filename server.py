from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from sqlalchemy import text

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///battleship.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

TEST_PASSWORD = "clemson-test-2026"


def check_test_auth():
    return request.headers.get("X-Test-Password") == TEST_PASSWORD


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
    status = db.Column(db.String(20), default="waiting", nullable=False)
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
# RESET
# full wipe so tests get clean IDs
# -------------------------

@app.route("/api/reset", methods=["POST"])
def reset():
    Move.query.delete()
    Ship.query.delete()
    GamePlayer.query.delete()
    Game.query.delete()
    Player.query.delete()

    # reset sqlite autoincrement counters
    db.session.execute(text("DELETE FROM sqlite_sequence WHERE name='game'"))
    db.session.execute(text("DELETE FROM sqlite_sequence WHERE name='player'"))
    db.session.execute(text("DELETE FROM sqlite_sequence WHERE name='ship'"))
    db.session.execute(text("DELETE FROM sqlite_sequence WHERE name='move'"))

    db.session.commit()
    return jsonify({"status": "reset"}), 200


# -------------------------
# CREATE PLAYER
# -------------------------

@app.route("/api/players", methods=["POST"])
def create_player():
    data = request.get_json(silent=True)
    if not data or "username" not in data:
        return jsonify({"error": "username required"}), 400

    username = data["username"]
    if not isinstance(username, str) or not username.strip():
        return jsonify({"error": "username required"}), 400

    existing = Player.query.filter_by(username=username).first()
    if existing:
        return jsonify({"error": "duplicate username"}), 400

    player = Player(username=username)
    db.session.add(player)
    db.session.commit()

    return jsonify({"player_id": player.id}), 201


# -------------------------
# PLAYER STATS
# -------------------------

@app.route("/api/players/<int:player_id>/stats", methods=["GET"])
def get_stats(player_id):
    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "not found"}), 404

    accuracy = 0
    if player.total_shots > 0:
        accuracy = player.total_hits / player.total_shots

    return jsonify({
        "games_played": player.games_played,
        "wins": player.wins,
        "losses": player.losses,
        "total_shots": player.total_shots,
        "total_hits": player.total_hits,
        "accuracy": accuracy
    }), 200


# -------------------------
# CREATE GAME
# -------------------------

@app.route("/api/games", methods=["POST"])
def create_game():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "invalid request"}), 400

    creator_id = data.get("creator_id")
    grid_size = data.get("grid_size")
    max_players = data.get("max_players")

    if creator_id is None or grid_size is None or max_players is None:
        return jsonify({"error": "missing fields"}), 400

    if not isinstance(grid_size, int) or grid_size < 5 or grid_size > 15:
        return jsonify({"error": "invalid grid size"}), 400

    if not isinstance(max_players, int) or max_players < 1:
        return jsonify({"error": "invalid max players"}), 400

    creator = Player.query.get(creator_id)
    if not creator:
        return jsonify({"error": "invalid creator"}), 403

    game = Game(
        grid_size=grid_size,
        max_players=max_players,
        status="waiting",
        current_turn_index=0
    )
    db.session.add(game)
    db.session.commit()

    db.session.add(GamePlayer(game_id=game.id, player_id=creator.id, turn_order=0))
    db.session.commit()

    return jsonify({"game_id": game.id, "status": "waiting"}), 201


# -------------------------
# JOIN GAME
# -------------------------

@app.route("/api/games/<int:game_id>/join", methods=["POST"])
def join_game(game_id):
    data = request.get_json(silent=True)
    if not data or "player_id" not in data:
        return jsonify({"error": "player_id required"}), 400

    player_id = data["player_id"]

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "game not found"}), 404

    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "invalid player"}), 403

    if GamePlayer.query.filter_by(game_id=game_id, player_id=player.id).first():
        return jsonify({"error": "already joined"}), 400

    count = GamePlayer.query.filter_by(game_id=game_id).count()
    if count >= game.max_players:
        return jsonify({"error": "game full"}), 409

    db.session.add(GamePlayer(
        game_id=game_id,
        player_id=player.id,
        turn_order=count
    ))
    db.session.commit()

    return jsonify({"status": "joined"}), 200


# -------------------------
# GET GAME
# -------------------------

@app.route("/api/games/<int:game_id>", methods=["GET"])
def get_game(game_id):
    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "game not found"}), 404

    active_players = GamePlayer.query.filter_by(game_id=game_id).count()

    return jsonify({
        "game_id": game.id,
        "grid_size": game.grid_size,
        "status": game.status,
        "current_turn_index": game.current_turn_index,
        "active_players": active_players
    }), 200


# -------------------------
# PLACE SHIPS
# exactly 3 single-cell ships
# -------------------------

@app.route("/api/games/<int:game_id>/place", methods=["POST"])
def place_ships(game_id):
    data = request.get_json(silent=True)
    if not data or "player_id" not in data or "ships" not in data:
        return jsonify({"error": "invalid request"}), 400

    player_id = data["player_id"]
    ship_list = data["ships"]

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "game not found"}), 404

    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "invalid player"}), 403

    if GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first() is None:
        return jsonify({"error": "player not in game"}), 403

    if Ship.query.filter_by(game_id=game_id, player_id=player_id).first():
        return jsonify({"error": "already placed"}), 400

    if not isinstance(ship_list, list) or len(ship_list) != 3:
        return jsonify({"error": "must place 3 ships"}), 400

    seen = set()
    for s in ship_list:
        row = s.get("row")
        col = s.get("col")

        if not isinstance(row, int) or not isinstance(col, int):
            return jsonify({"error": "invalid coordinates"}), 400

        if row < 0 or row >= game.grid_size or col < 0 or col >= game.grid_size:
            return jsonify({"error": "out of bounds"}), 400

        if (row, col) in seen:
            return jsonify({"error": "duplicate ship placement"}), 400

        seen.add((row, col))

    for row, col in seen:
        db.session.add(Ship(
            game_id=game_id,
            player_id=player_id,
            row=row,
            col=col
        ))

    db.session.commit()

    placed = db.session.query(Ship.player_id)\
        .filter_by(game_id=game_id)\
        .group_by(Ship.player_id)\
        .count()

    total = GamePlayer.query.filter_by(game_id=game_id).count()

    if placed == total:
        game.status = "active"
        db.session.commit()

    return jsonify({"status": "placed"}), 200


# -------------------------
# FIRE
# -------------------------

@app.route("/api/games/<int:game_id>/fire", methods=["POST"])
def fire(game_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "invalid request"}), 400

    player_id = data.get("player_id")
    row = data.get("row")
    col = data.get("col")

    if player_id is None or row is None or col is None:
        return jsonify({"error": "missing fields"}), 400

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "game not found"}), 404

    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "invalid player"}), 403

    if GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first() is None:
        return jsonify({"error": "player not in game"}), 403

    if game.status == "finished":
        return jsonify({"error": "game finished"}), 409

    if game.status != "active":
        return jsonify({"error": "not active"}), 400

    if not isinstance(row, int) or not isinstance(col, int):
        return jsonify({"error": "invalid coordinates"}), 400

    if row < 0 or row >= game.grid_size or col < 0 or col >= game.grid_size:
        return jsonify({"error": "out of bounds"}), 400

    existing_move = Move.query.filter_by(game_id=game_id, row=row, col=col).first()
    if existing_move:
        return jsonify({"error": "duplicate move"}), 400

    players_in_game = GamePlayer.query.filter_by(game_id=game_id)\
        .order_by(GamePlayer.turn_order).all()

    if not players_in_game:
        return jsonify({"error": "game has no players"}), 400

    current = players_in_game[game.current_turn_index].player_id
    if current != player_id:
        return jsonify({"error": "not your turn"}), 403

    hit_ship = Ship.query.filter_by(
        game_id=game_id,
        row=row,
        col=col
    ).first()

    result = "hit" if hit_ship else "miss"

    if hit_ship:
        db.session.delete(hit_ship)

    db.session.add(Move(
        game_id=game_id,
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
        remaining = Ship.query.filter_by(game_id=game_id, player_id=gp.player_id).count()
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
        remaining = Ship.query.filter_by(game_id=game_id, player_id=pid).count()
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

@app.route("/api/games/<int:game_id>/moves", methods=["GET"])
def get_moves(game_id):
    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "game not found"}), 404

    rows = Move.query.filter_by(game_id=game_id).order_by(Move.id).all()
    payload = []
    for m in rows:
        payload.append({
            "player_id": m.player_id,
            "row": m.row,
            "col": m.col,
            "result": m.result,
            "timestamp": m.timestamp
        })

    return jsonify(payload), 200


# -------------------------
# TEST RESTART
# preserve player stats
# -------------------------

@app.route("/api/test/games/<int:game_id>/restart", methods=["POST"])
def test_restart(game_id):
    if not check_test_auth():
        return jsonify({"error": "forbidden"}), 403

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "not found"}), 404

    Ship.query.filter_by(game_id=game_id).delete()
    Move.query.filter_by(game_id=game_id).delete()

    game.status = "waiting"
    game.current_turn_index = 0

    db.session.commit()

    return jsonify({"status": "restarted"}), 200


# -------------------------
# TEST PLACE SHIPS
# deterministic grading support
# -------------------------

@app.route("/api/test/games/<int:game_id>/ships", methods=["POST"])
def test_place_ships(game_id):
    if not check_test_auth():
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True)
    if not data or "player_id" not in data or "ships" not in data:
        return jsonify({"error": "invalid request"}), 400

    player_id = data["player_id"]
    ship_list = data["ships"]

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "game not found"}), 404

    if Player.query.get(player_id) is None:
        return jsonify({"error": "invalid player"}), 403

    if GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first() is None:
        return jsonify({"error": "player not in game"}), 403

    if game.status == "finished":
        return jsonify({"error": "game finished"}), 409

    Ship.query.filter_by(game_id=game_id, player_id=player_id).delete()

    seen = set()
    for s in ship_list:
        row = s.get("row")
        col = s.get("col")

        if not isinstance(row, int) or not isinstance(col, int):
            return jsonify({"error": "invalid coordinates"}), 400

        if row < 0 or row >= game.grid_size or col < 0 or col >= game.grid_size:
            return jsonify({"error": "out of bounds"}), 400

        if (row, col) in seen:
            return jsonify({"error": "duplicate ship placement"}), 400

        seen.add((row, col))

    for row, col in seen:
        db.session.add(Ship(
            game_id=game_id,
            player_id=player_id,
            row=row,
            col=col
        ))

    db.session.commit()

    placed = db.session.query(Ship.player_id)\
        .filter_by(game_id=game_id)\
        .group_by(Ship.player_id)\
        .count()

    total = GamePlayer.query.filter_by(game_id=game_id).count()

    if placed == total:
        game.status = "active"
        db.session.commit()

    return jsonify({"status": "ok"}), 200


# -------------------------
# TEST BOARD REVEAL
# -------------------------

@app.route("/api/test/games/<int:game_id>/board/<int:player_id>", methods=["GET"])
def test_board(game_id, player_id):
    if not check_test_auth():
        return jsonify({"error": "forbidden"}), 403

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "game not found"}), 404

    if Player.query.get(player_id) is None:
        return jsonify({"error": "invalid player"}), 403

    ships_rows = Ship.query.filter_by(game_id=game_id, player_id=player_id).all()
    moves_rows = Move.query.filter_by(game_id=game_id).order_by(Move.id).all()

    ships_payload = []
    for s in ships_rows:
        ships_payload.append([s.row, s.col])

    moves_payload = []
    for m in moves_rows:
        moves_payload.append({
            "player_id": m.player_id,
            "row": m.row,
            "col": m.col,
            "result": m.result,
            "timestamp": m.timestamp
        })

    return jsonify({
        "ships": ships_payload,
        "moves": moves_payload
    }), 200


# -------------------------
# INIT
# -------------------------

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)