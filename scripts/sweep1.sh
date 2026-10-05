for spec in "mcts:sims=400,det=4" "mcts:sims=400,det=4,scale=30" "mcts:sims=400,det=4,scale=30,c=0.3" "mcts:sims=400,det=4,scale=15,c=0.5" "mcts:sims=400,det=1,scale=30"; do
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/run_match.py "$spec" greedy --seeds 12 --workers 11
done
