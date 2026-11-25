"""Domain-native mechanical equations. SI inputs; margins retain their units."""
import math


def ground(p, x):
    v = abs(x['speed_m_s'])
    a = p['brake_decel_m_s2'] * x['traction_fraction']
    if a <= 0 and v > 0:
        return {'stopping_distance_m': None, 'clearance_margin_m': None,
                'yaw_rate_rad_s': (x['right_wheel_m_s']-x['left_wheel_m_s'])/p['track_m'],
                'wheel_speed_residual_m_s': x['speed_m_s']-(x['right_wheel_m_s']+x['left_wheel_m_s'])/2}
    stop = 0 if v == 0 else v*p['latency_s'] + v*v/(2*a)
    return {'stopping_distance_m': stop, 'clearance_margin_m': x['clearance_m']-stop,
            'yaw_rate_rad_s': (x['right_wheel_m_s']-x['left_wheel_m_s'])/p['track_m'],
                'wheel_speed_residual_m_s': x['speed_m_s']-(x['right_wheel_m_s']+x['left_wheel_m_s'])/2}


def vessel(p, x):
    v = x['speed_m_s']
    drag = .5*p['density_kg_m3']*p['drag_area_m2']*v*v
    net = p['thrust_n']*x['throttle_fraction']-drag
    return {'drag_n': drag, 'net_force_n': net,
            'acceleration_m_s2': net/p['mass_kg'], 'propulsive_power_w': drag*v}


def aircraft(p, x):
    q = .5*x['density_kg_m3']*x['speed_m_s']**2
    return {'dynamic_pressure_pa': q, 'lift_n': q*p['area_m2']*x['lift_coefficient'],
            'drag_n': q*p['area_m2']*x['drag_coefficient'],
            'load_margin_pa': p['q_limit_pa']-q}


def rotorcraft(p, x):
    thrust = p['max_thrust_n']*x['throttle_fraction']**2
    weight = p['mass_kg']*p['gravity_m_s2']
    return {'thrust_n': thrust, 'weight_n': weight,
            'vertical_acceleration_m_s2': (thrust-weight)/p['mass_kg'],
            'thrust_margin_n': thrust-weight}


def humanoid(p, x):
    omega = math.sqrt(p['gravity_m_s2']/x['com_height_m'])
    cp = x['com_x_m']+x['com_velocity_m_s']/omega
    residual = x['friction_coefficient']*x['normal_force_n']-abs(x['tangent_force_n'])
    return {'capture_point_m': cp, 'support_margin_m': p['support_half_width_m']-abs(cp),
            'friction_margin_n': residual}


def manipulator(p, x):
    demand = x['joint_torque_nm']
    margin = [limit-abs(t) for limit,t in zip(p['torque_limits_nm'], demand)]
    error = [a-b for a,b in zip(x['measured_joint_rad'],x['desired_joint_rad'])]
    return {'joint_torque_margin_nm': margin, 'minimum_torque_margin_nm': min(margin),
            'tracking_error_rad': error, 'maximum_tracking_error_rad': max(map(abs,error))}


def launch(p, x):
    thrust = p['engine_count']*p['engine_thrust_n']*x['throttle_fraction']
    weight = x['mass_kg']*p['gravity_m_s2']
    return {'cluster_thrust_n': thrust, 'weight_n': weight,
            'thrust_to_weight': thrust/weight, 'vertical_force_margin_n': thrust-weight}
