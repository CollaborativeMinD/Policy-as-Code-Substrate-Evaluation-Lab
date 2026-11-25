"""RF, orbital geometry, and power balance; no forced cross-domain vector."""
import math


def radar(p, x):
    c = 299792458.0
    wavelength = c/x['frequency_hz']
    loss = (4*math.pi*x['range_m']/wavelength)**2
    snr = 10**(x['snr_db']/10)
    return {'wavelength_m': wavelength, 'range_resolution_m': c/(2*x['bandwidth_hz']),
            'free_space_loss_db': 10*math.log10(loss),
            'channel_capacity_bit_s': x['bandwidth_hz']*math.log1p(snr)/math.log(2),
            'snr_margin_db': x['snr_db']-p['required_snr_db']}


def coverage(p, x):
    r = p['radius_m']; h = x['altitude_m']; e = math.radians(x['elevation_deg'])
    angle = math.acos(max(-1,min(1,r/(r+h)*math.cos(e))))-e
    angle = max(0, angle)
    period = 2*math.pi*math.sqrt((r+h)**3/p['mu_m3_s2'])
    fraction = math.sin(angle/2)**2
    return {'orbital_period_s': period, 'coverage_half_angle_rad': angle,
            'surface_fraction': fraction, 'footprint_area_m2': 4*math.pi*r*r*fraction}


def spacecraft(p, x):
    available = p['array_power_w']*(1-x['eclipse_fraction'])*max(0,math.cos(math.radians(x['sun_angle_deg'])))
    net = available-x['load_w']
    dv = p['thrust_n']*x['burn_duration_s']/p['mass_kg']
    return {'available_power_w': available, 'power_margin_w': net,
            'small_burn_delta_v_m_s': dv,
            'reserve_time_s': None if net >= 0 else x['usable_energy_wh']*3600/(-net)}


def containment(p, x):
    rate = (x['heat_in_w']-p['heat_removal_w'])/p['thermal_capacity_j_k']
    temp = x['initial_temp_k']+rate*x['duration_s']
    horizon = None if rate <= 0 else max(0,(p['temp_limit_k']-x['initial_temp_k'])/rate)
    if x['initial_temp_k'] >= p['temp_limit_k']:
        horizon = 0.0
    return {'temperature_rate_k_s': rate, 'temperature_k': temp,
            'thermal_margin_k': p['temp_limit_k']-temp, 'time_to_limit_s': horizon}
