# battleship-cpsc3750
CPSC 3750 Final Project

## Project overview
A RESTful multiplayer Battleship server supporting 1–N players, configurable grid sizes, persistent player statistics, and full turn-based gameplay. Built with Python/Flask and MySQL.

## Architecture summary
The server follows a layered architecture:
- **Flask** handles HTTP routing via Blueprints (players, games, test mode)
- **MySQL** provides persistent relational storage
- **Game logic** is isolated in a dedicated module for validation, turn rotation, and elimination
- **Test mode** endpoints are gated behind an `X-Test-Mode` header for autograder access
```
battleship/
├── app.py              # Flask entry point + blueprint registration
├── db/
│   ├── connection.py   # MySQL connection context manager
│   └── schema.sql      # Full relational schema
├── models/
│   └── game_logic.py   # Ship validation, turn rotation, elimination
├── routes/
│   ├── players.py      # Player registration and stats
│   ├── games.py        # Game lifecycle and moves
│   └── test_mode.py    # Deterministic test endpoints (X-Test-Mode protected)
├── tests.py            # Phase 1 test suite
├── requirements.txt
└── .env.example
```

## API description

### Players
| Method | Endpoint | Description |
|---|---|---|
| POST | `/players` | Register a new player |
| GET | `/players` | List all players |
| GET | `/players/:id` | Get player profile and stats |

### Games
| Method | Endpoint | Description |
|---|---|---|
| POST | `/games` | Create a new game |
| GET | `/games` | List all games |
| GET | `/games/:id` | Get game state and players |
| POST | `/games/:id/join` | Join a game |
| POST | `/games/:id/ships` | Place ships manually |
| POST | `/games/:id/ships/random` | Place ships randomly |
| POST | `/games/:id/start` | Start the game |
| POST | `/games/:id/move` | Fire a shot |
| GET | `/games/:id/moves` | Get full move log |

### Test Mode (requires `X-Test-Mode` header — returns 403 without it)
| Method | Endpoint | Description |
|---|---|---|
| POST | `/test/games/:id/ships` | Deterministic ship placement for autograder |
| GET | `/test/games/:id/board` | Reveal full board state |
| POST | `/test/games/:id/reset` | Reset game state, preserve player stats |
| POST | `/test/games/:id/set-turn` | Force turn for concurrency testing |

## Team member 
- Jade Ashley
- Ayden Sabol

## AI tool(s) used
Claude 
Chat GPT 

## Major role of each human + AI
Jade Ashley - Frontend design, SQL database design and schema implementation 
Ayden Sabol - Backend design, server architecture, API route implementation 
Claude - Setup guidance, debugging, explaining requirements, finding and fixing issues when they occur 
Chat GPT - Code suggestions and implementation support 

```bash
pip install -r requirements.txt
cp .env.example .env        # add your MySQL credentials
mysql -u root -p < db/schema.sql
python app.py               # runs on http://localhost:5000
python -m pytest tests.py -v
```
