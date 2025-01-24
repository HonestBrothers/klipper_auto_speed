import re
import sys
import os

from klipper.klippy.extras.trad_rack import TradRackToolHead

class AutoSpeed:
    def __init__(self, config):
        self.config = config
        self.min_cruise_ratio = TradRackToolHead(config).minimum_cruise_ratio

    # Trapezoidal acceleration profile - best estimate
    def trapezoidal_motion_time(self, vmax, a, d_total):
        # Acceleration phase
        t_acc = vmax / a
        d_acc = 0.5 * a * t_acc**2

        # Deceleration phase
        t_dec = vmax / a
        d_dec = 0.5 * a * t_dec**2

        # Constant velocity phase
        d_const = d_total - (d_acc + d_dec)

        # Constant velocity portion of the phase
        d_ratio = d_const / d_total

        # If the constant velocity portion of the phase is less than the minimum cruise ratio
        if d_ratio < self.min_cruise_ratio:
            # If the constant velocity portion of the phase is 0
            if d_ratio == 0:
                t_acc = (2 * d_total / a)**0.5
                t_dec = t_acc
                t_const = 0
            #Constant velocity phase is not 0. Set constant velocity portion of the move to minimum cruise ratio distance, then determine acceleration and deceleration times based on the time left.
            else:
                d_const = self.min_cruise_ratio * d_total
                t_const = d_const / vmax
                t_acc = (2 * d_const / a)**0.5
                t_dec = t_acc
        # Constant velocity portion of the phase is greater than the minimum cruise ratio
        else:
            t_const = d_const / vmax

        # Total time
        t_total = t_acc + t_const + t_dec
        return t_total

    def interpolate_acceleration(self, velocity_acceleration_pairs, velocity):
        min_velocity = velocity_acceleration_pairs[0][0]
        max_velocity = velocity_acceleration_pairs[-1][0]

        if velocity < min_velocity:
            acceleration_x, acceleration_y = velocity_acceleration_pairs[0][1], velocity_acceleration_pairs[0][2]
        elif velocity > max_velocity:
            acceleration_x, acceleration_y = velocity_acceleration_pairs[-1][1], velocity_acceleration_pairs[-1][2]
        else:
            for i in range(len(velocity_acceleration_pairs) - 1):
                v1, a1_x, a1_y = velocity_acceleration_pairs[i]
                v2, a2_x, a2_y = velocity_acceleration_pairs[i+1]
                if v1 <= velocity <= v2:
                    acceleration_x = int((velocity - v1) * (a2_x - a1_x) / (v2 - v1) + a1_x)
                    acceleration_y = int((velocity - v1) * (a2_y - a1_y) / (v2 - v1) + a1_y)
                    return acceleration_x, acceleration_y

        return acceleration_x, acceleration_y

    def read_velocity_acceleration_pairs(self, file_path):
        velocity_acceleration_pairs = []
        use_individual_acceleration = False

        try:
            with open(file_path, 'r') as config_file:
                capture_values = False
                for line in config_file:
                    line = line.strip()
                    if line.startswith("#*# Axis: X") or line.startswith("#*# Axis: Y"):
                        capture_values = True
                        use_individual_acceleration = True
                    elif line.startswith("#*# End of"):
                        capture_values = False
                    elif capture_values:
                        values = line.lstrip("#*#").strip().split(',')
                        if line.startswith("#*# Axis: X"):
                            velocity, acceleration_x = map(int, values)
                            velocity_acceleration_pairs.append((velocity, acceleration_x, None))
                        elif line.startswith("#*# Axis: Y"):
                            velocity, acceleration_y = map(int, values)
                            velocity_acceleration_pairs.append((velocity, None, acceleration_y))
                        else:
                            velocity, acceleration = map(int, values)
                            velocity_acceleration_pairs.append((velocity, acceleration, acceleration))
                            use_individual_acceleration = False

        except FileNotFoundError:
            print(f'File not found: {file_path}')
        except Exception as e:
            print(f'Error: {str(e)}')

        return velocity_acceleration_pairs, use_individual_acceleration

    def process_gcode(self, input_filename, velocity_acceleration_pairs, use_individual_acceleration):
        try:
            with open(input_filename, 'r') as input_file:
                base_name, extension = os.path.splitext(input_filename)
                output_filename = f'{base_name}_parsed{extension}'

                with open(output_filename, 'w') as output_file:
                    for line in input_file:
                        match = re.search(r'G1', line)
                        if match:
                            velocity_mm_per_min = int(re.search(r'F(\d+)', line))
                            velocity_mm_per_sec = velocity_mm_per_min / 60

                            distance_x_match = re.search(r'X(-?\d+)', line)
                            distance_y_match = re.search(r'Y(-?\d+)', line)

                            distance_x_mm = float(distance_x_match.group(1)) if distance_x_match else None
                            distance_y_mm = float(distance_y_match.group(1)) if distance_y_match else None

                            #Call trapezoidal_motion_time to and pick the minimum amount of time to complete the move by reducing the velocity. Consider velocity_mm_per_sec as the maximum velocity. Use the interpolated acceleration values to write a new velocity and acceleration command to the output file

                            # Define range for velocities to test
                            velocity_range = range(10, int(velocity_mm_per_sec) + 1, 10)  # Example range from 10 to max velocity in steps of 10 mm/s
                            min_t_total = float('inf')
                            best_velocity = velocity_mm_per_sec

                            for v in velocity_range:
                                acceleration_x, acceleration_y = self.interpolate_acceleration(velocity_acceleration_pairs, velocity_mm_per_sec)
                                t_total_x = self.trapezoidal_motion_time(v, acceleration_x, distance_x_mm)
                                t_total_y = self.trapezoidal_motion_time(v, acceleration_y, distance_y_mm)
                                # Pick the slower time to complete the move between the X and Y moves, so one doesn't outrun the other.
                                t_total = max(t_total_x, t_total_y)
                                if t_total < min_t_total:
                                    min_t_total = t_total
                                    best_velocity = v

                            # Write the new velocity and acceleration command to the output file
                            velocity_mm_per_sec = best_velocity
                            velocity_mm_per_min = int(velocity_mm_per_sec * 60)

                            acceleration_x, acceleration_y = self.interpolate_acceleration(velocity_acceleration_pairs, velocity_mm_per_sec)

                            output_file.write(f'G1 F{velocity_mm_per_min}\n')
                            if use_individual_acceleration:
                                output_file.write(f'SET_KINEMATICS_LIMIT X_ACCEL={acceleration_x} Y_ACCEL={acceleration_y}\n')
                            else:
                                output_file.write(f'SET_VELOCITY_LIMIT ACCEL={acceleration_y}\n')
                        #elif line.startswith('M201'):
                        #    match_x = re.search(r'X(\d+)', line)
                        #    match_y = re.search(r'Y(\d+)', line)
                        #    if match_x:
                        #        int(match_x.group(1))
                        #    if match_y:
                        #        int(match_y.group(1))
                        #    output_file.write(line)
                        else:
                            output_file.write(line)

            print(f'The G-code file was successfully created: {output_filename}')
        except FileNotFoundError:
            print(f'File not found: {input_filename}')
        except Exception as e:
            print(f'Error: {str(e)}')

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python gcode_parser.py <input file>')
    else:
        #clean this section up
        input_filename = sys.argv[1]
        config = {}  # Define config as an empty dictionary or load it from a file if needed
        config_path = "/home/pi/printer_data/config/autoacc.cfg"
        auto_speed = AutoSpeed(config)
        velocity_acceleration_pairs, use_individual_acceleration = auto_speed.read_velocity_acceleration_pairs(config_path)

        if velocity_acceleration_pairs:
            auto_speed.process_gcode(input_filename, velocity_acceleration_pairs, use_individual_acceleration)
        else:
            print("Speed-acceleration pairs could not be read from the configuration file.")
