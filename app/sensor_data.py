import random


class AnalogSensor:

    def __init__(
        self,
        initial,
        minimum,
        maximum,
        drift,
        noise,
        spike_probability=0.003,
        spike_size=5
    ):

        self.value = initial
        self.minimum = minimum
        self.maximum = maximum
        self.drift = drift
        self.noise = noise
        self.spike_probability = spike_probability
        self.spike_size = spike_size

    def read(self):

        # Slow process movement
        self.value += random.uniform(-self.drift, self.drift)

        # Instrument noise
        self.value += random.gauss(0, self.noise)

        # Sudden spike
        if random.random() < self.spike_probability:

            direction = random.choice([-1, 1])

            spike = direction * random.uniform(
                self.spike_size * 0.5,
                self.spike_size
            )

            self.value += spike

        self.value = max(
            self.minimum,
            min(self.maximum, self.value)
        )

        return round(self.value, 2)

sensors = {

    # =======================
    # VRM
    # =======================

    # Mill inlet temperature
    "VRM-TT-030": AnalogSensor(
        initial=210, minimum=50, maximum=300,
        drift=0.5, noise=0.20, spike_probability=0.003, spike_size=15
    ),

    # Mill outlet temperature (no alarms — monitoring only)
    "VRM-TT-031": AnalogSensor(
        initial=165, minimum=40, maximum=280,
        drift=0.35, noise=0.15, spike_probability=0.002, spike_size=10
    ),

    "VRM-VT-040": AnalogSensor(
        initial=2.5, minimum=0, maximum=15,
        drift=0.05, noise=0.03, spike_probability=0.004, spike_size=2
    ),

    "VRM-VT-041": AnalogSensor(
        initial=1.8, minimum=0, maximum=12,
        drift=0.03, noise=0.02, spike_probability=0.003, spike_size=1.5
    ),

    "VRM-VT-042": AnalogSensor(
        initial=1.5, minimum=0, maximum=10,
        drift=0.03, noise=0.02, spike_probability=0.003, spike_size=1.2
    ),

    "VRM-PT-060": AnalogSensor(
        initial=180, minimum=120, maximum=250,
        drift=0.20, noise=0.10, spike_probability=0.002, spike_size=8
    ),

    # =======================
    # GCT
    # =======================

    "GCT-TT-101": AnalogSensor(
        initial=240, minimum=80, maximum=450,
        drift=0.60, noise=0.25, spike_probability=0.004, spike_size=18
    ),

    "GCT-TT-102": AnalogSensor(
        initial=90, minimum=50, maximum=180,
        drift=0.40, noise=0.20, spike_probability=0.003, spike_size=12
    ),

    # Air flow (L/min) — matches seed l1=800, l2=500
    "GCT-FT-201": AnalogSensor(
        initial=900, minimum=0, maximum=1500,
        drift=8, noise=2, spike_probability=0.003, spike_size=80
    ),

    # Water flow (L/min) — matches seed l1=5, l2=2, h1=25, h2=30
    "GCT-FT-202": AnalogSensor(
        initial=15, minimum=0, maximum=40,
        drift=0.5, noise=0.2, spike_probability=0.003, spike_size=4
    ),

    # =======================
    # KBF
    # =======================

    # Differential pressure (mbar) — matches seed l1=2, l2=1, h1=15, h2=18
    "KBF-DP-800": AnalogSensor(
        initial=8, minimum=0, maximum=25,
        drift=0.3, noise=0.15, spike_probability=0.003, spike_size=3
    ),

    "KBF-VT-802": AnalogSensor(
        initial=1.2, minimum=0, maximum=8,
        drift=0.02, noise=0.02, spike_probability=0.003, spike_size=1
    ),

    "KBF-TT-803": AnalogSensor(
        initial=45, minimum=20, maximum=120,
        drift=0.2, noise=0.1, spike_probability=0.003, spike_size=6
    ),

    # Air receiver pressure (mbar) — matches seed l1=5.5, l2=4.5
    "KBF-PT-804": AnalogSensor(
        initial=7, minimum=0, maximum=12,
        drift=0.1, noise=0.05, spike_probability=0.002, spike_size=1
    )
}