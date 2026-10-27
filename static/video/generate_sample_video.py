import cv2
import numpy as np
import os
import random

def create_sample_traffic_video(output_path="static/video/traffic_demo.mp4", duration_sec=15, fps=25):
    """
    Creates an animated sample traffic video simulating road lane traffic with moving vehicle shapes.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    width, height = 800, 480
    total_frames = duration_sec * fps

    # Define VideoWriter (MP4V / XVID)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    if not out.isOpened():
        # Fallback to AVI if MP4 fails
        output_path = output_path.replace('.mp4', '.avi')
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    print(f"[Video Synthesizer] Generating {duration_sec}s demo traffic video at {output_path}...")

    # Vehicle objects: (x, y, speed, width, height, color, label)
    vehicles = [
        {'x': random.randint(-200, 0), 'y': 180, 'speed': 6, 'w': 90, 'h': 45, 'color': (50, 205, 50), 'label': 'Car'},
        {'x': random.randint(-400, -100), 'y': 240, 'speed': 4, 'w': 160, 'h': 65, 'color': (255, 140, 0), 'label': 'Bus'},
        {'x': random.randint(-300, 0), 'y': 310, 'speed': 7, 'w': 85, 'h': 40, 'color': (255, 215, 0), 'label': 'Car'},
        {'x': random.randint(-500, -200), 'y': 370, 'speed': 5, 'w': 140, 'h': 60, 'color': (30, 144, 255), 'label': 'Truck'},
        {'x': random.randint(-200, 0), 'y': 140, 'speed': 8, 'w': 50, 'h': 30, 'color': (255, 20, 147), 'label': 'Motorbike'},
        {'x': random.randint(-600, -300), 'y': 250, 'speed': 6, 'w': 95, 'h': 48, 'color': (147, 112, 219), 'label': 'Car'},
        {'x': random.randint(-700, -400), 'y': 320, 'speed': 5, 'w': 100, 'h': 50, 'color': (60, 179, 113), 'label': 'Car'},
    ]

    for frame_idx in range(total_frames):
        # Asphalt Road Background
        frame = np.full((height, width, 3), (50, 50, 50), dtype=np.uint8)

        # Grass borders
        frame[0:100, :] = (40, 120, 40)
        frame[420:480, :] = (40, 120, 40)

        # Road Markings (Yellow & White Lanes)
        cv2.line(frame, (0, 100), (width, 100), (255, 255, 255), 3)
        cv2.line(frame, (0, 420), (width, 420), (255, 255, 255), 3)

        # Dashed Lane Dividers
        dash_offset = (frame_idx * 5) % 40
        for y_lane in [170, 250, 330]:
            for x_dash in range(-dash_offset, width + 40, 40):
                cv2.line(frame, (x_dash, y_lane), (x_dash + 20, y_lane), (200, 200, 200), 2)

        # Draw moving vehicles
        for v in vehicles:
            v['x'] += v['speed']
            if v['x'] > width + 50:
                v['x'] = -random.randint(100, 400)
                v['speed'] = random.randint(4, 9)

            vx, vy, vw, vh = int(v['x']), int(v['y']), int(v['w']), int(v['h'])

            # Vehicle Body
            cv2.rectangle(frame, (vx, vy), (vx + vw, vy + vh), v['color'], -1)
            cv2.rectangle(frame, (vx, vy), (vx + vw, vy + vh), (0, 0, 0), 2)

            # Windshield / Roof Detail
            cv2.rectangle(frame, (vx + int(vw * 0.2), vy + int(vh * 0.15)), 
                          (vx + int(vw * 0.7), vy + int(vh * 0.85)), (220, 220, 220), -1)

            # Headlights
            cv2.circle(frame, (vx + vw - 2, vy + 6), 4, (0, 255, 255), -1)
            cv2.circle(frame, (vx + vw - 2, vy + vh - 6), 4, (0, 255, 255), -1)

        out.write(frame)

    out.release()
    print(f"[Video Synthesizer] Sample traffic video generated successfully ({output_path}).")
    return output_path

if __name__ == '__main__':
    create_sample_traffic_video()
