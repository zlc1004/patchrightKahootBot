Xvfb :0 -screen 0 1920x1080x24 &
export DISPLAY=:0
x11vnc -display :0 -nopw -listen 0.0.0.0 -forever &
python serve.py