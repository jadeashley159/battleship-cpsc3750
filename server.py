from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

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
    grid_size = db.Column(db.Integer)
    max_players = db.Column(db.Integer)
    status = db.Column(db.String(20), default="waiting")
    current_turn_index = db.Column(db.Integer, default=0)

class GamePlayer(db.Model):
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), primary_key=True)
    turn_order = db.Column(db.Integer)

class Ship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer)
    player_id = db.Column(db.Integer)
    row = db.Column(db.Integer)
    col = db.Column(db.Integer)

class Move(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer)
    player_id = db.Column(db.Integer)
    row = db.Column(db.Integer)
    col = db.Column(db.Integer)
    result = db.Column(db.String(10))
    timestamp = db.Column(db.String(50))

# -------------------------
# RESET (DOES NOT DELETE PLAYERS)
# -------------------------

@app.route("/api/reset", methods=["POST"])
def reset():
    Move.query.delete()
    Ship.query.delete()
    GamePlayer.query.delete()
    Game.query.delete()
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

    if Player.query.filter_by(username=data["username"]).first():
        return jsonify({"error": "duplicate username"}), 400

    player = Player(username=data["username"])
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
    })

# -------------------------
# CREATE GAME
# -------------------------

@app.route("/api/games", methods=["POST"])
def create_game():
    data = request.get_json(silent=True)

    creator = Player.query.get(data.get("creator_id"))
    if not creator:
        return jsonify({"error": "invalid creator"}), 403

    game = Game(
        grid_size=data["grid_size"],
        max_players=data["max_players"]
    )
    db.session.add(game)
    db.session.commit()

    gp = GamePlayer(game_id=game.id, player_id=creator.id, turn_order=0)
    db.session.add(gp)
    db.session.commit()

    return jsonify({"game_id": game.id, "status": "waiting"}), 201

# -------------------------
# JOIN GAME
# -------------------------

@app.route("/api/games/<int:game_id>/join", methods=["POST"])
def join_game(game_id):
    data = request.get_json(silent=True)
    player = Player.query.get(data.get("player_id"))
    game = Game.query.get(game_id)

    if not game:
        return jsonify({"error": "game not found"}), 404
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
# PLACE SHIPS
# -------------------------

@app.route("/api/games/<int:game_id>/place", methods=["POST"])
def place_ships(game_id):
    data = request.get_json(silent=True)
    player_id = data["player_id"]

    game = Game.query.get(game_id)

    if Ship.query.filter_by(game_id=game_id, player_id=player_id).first():
        return jsonify({"error": "already placed"}), 400

    for s in data["ships"]:
        db.session.add(Ship(
            game_id=game_id,
            player_id=player_id,
            row=s["row"],
            col=s["col"]
        ))

    db.session.commit()

    placed = db.session.query(Ship.player_id).filter_by(game_id=game_id).distinct().count()
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
    player_id = data["player_id"]

    game = Game.query.get(game_id)

    if game.status != "active":
        return jsonify({"error": "not active"}), 400

    players = GamePlayer.query.filter_by(game_id=game_id).order_by(GamePlayer.turn_order).all()
    current = players[game.current_turn_index].player_id

    if current != player_id:
        return jsonify({"error": "not your turn"}), 403

    hit_ship = Ship.query.filter_by(
        game_id=game_id,
        row=data["row"],
        col=data["col"]
    ).first()

    result = "hit" if hit_ship else "miss"

    if hit_ship:
        db.session.delete(hit_ship)

    db.session.add(Move(
        game_id=game_id,
        player_id=player_id,
        row=data["row"],
        col=data["col"],
        result=result,
        timestamp=datetime.utcnow().isoformat()
    ))

    player = Player.query.get(player_id)
    player.total_shots += 1
    if result == "hit":
        player.total_hits += 1

    db.session.commit()

    remaining = Ship.query.filter(Ship.game_id == game_id).count()

    if remaining == 0:
        game.status = "finished"
        for gp in players:
            p = Player.query.get(gp.player_id)
            p.games_played += 1
            if gp.player_id == player_id:
                p.wins += 1
            else:
                p.losses += 1

        db.session.commit()

        return jsonify({
            "result": result,
            "game_status": "finished",
            "winner_id": player_id
        })

    game.current_turn_index = (game.current_turn_index + 1) % len(players)
    db.session.commit()

    return jsonify({
        "result": result,
        "next_player_id": players[game.current_turn_index].player_id,
        "game_status": "active"
    })

# -------------------------
# RUN
# -------------------------

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)