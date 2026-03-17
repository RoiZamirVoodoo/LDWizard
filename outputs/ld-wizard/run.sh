#!/bin/bash
echo ""
echo "  Installing dependencies..."
pip3 install -r requirements.txt --quiet
echo ""
echo "  Starting LD Wizard..."
echo "  Open your browser at: http://127.0.0.1:5050"
echo ""
python3 app.py
