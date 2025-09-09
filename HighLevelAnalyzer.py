# HighLevelAnalyzer.py
# HLA for SPI with LLA set to 4 bits.
# Rules for each CS cycle:
#  - 1 nibble  -> nibble_ok (4-bit command)
#  - >1 nibble -> merge in pairs -> byte_ok (8-bit)
#  - odd>1     -> byte + leftover nibble (nibble_ok) + error (strict)
#  - Anomalies:
#       * <4 total clocks (no nibble seen) -> error
#       * clocks not multiple of 8 (except 4) -> error
#       * odd nibble count (>1) on MOSI/MISO -> error

from saleae.analyzers import HighLevelAnalyzer, AnalyzerFrame

class Spi4or8ByCsHla(HighLevelAnalyzer):
    result_types = {
        'packet':     {'format': '{{data.dir}}: {{data.info}}'},
        'nibble_ok':  {'format': '{{data.dir}} 4b = {{data.val}}'},
        'byte_ok':    {'format': '{{data.dir}} 8b = {{data.val}}'},
        'error':      {'format': 'ERROR: {{data.msg}}'},
    }

    def __init__(self):
        # merge: first nibble = HIGH, second = LOW
        self._merge_order = 'high_then_low'
        self._reset_cs_state()

    # ---------- internals ----------
    def _reset_cs_state(self):
        self.cs_active = False
        self.cs_start  = None
        # lists of tuples (val, start_time, end_time)
        self.mosi_nibbles = []
        self.miso_nibbles = []

    def _merge_pair(self, a, b):
        # a,b: 0..15
        if self._merge_order == 'high_then_low':
            return ((a & 0xF) << 4) | (b & 0xF)
        else:
            return ((b & 0xF) << 4) | (a & 0xF)

    def _build_items_for_dir(self, dir_label, nibbles):
        """
        Converts collected nibbles into "items" (placeholders).
        Returns a list of dict: {'dir','kind','val','key_time'}
        """
        items = []
        n = len(nibbles)
        if n == 0:
            return items

        if n == 1:
            v, s, e = nibbles[0]
            items.append({'dir': dir_label, 'kind': 'nibble_ok', 'val': v, 'key_time': s})
            return items

        i = 0
        while i + 1 < n:
            (a, s1, _), (b, _, e2) = nibbles[i], nibbles[i+1]
            byte_val = self._merge_pair(a, b)
            items.append({'dir': dir_label, 'kind': 'byte_ok', 'val': byte_val, 'key_time': s1})
            i += 2

        if i < n:
            v, s, e = nibbles[i]
            items.append({'dir': dir_label, 'kind': 'nibble_ok', 'val': v, 'key_time': s})

        return items

    def _build_error_items(self, cs_start, end_time):
        """
        Create possible 'error' items (key_time=cs_start to show them at the beginning).
        Rules:
          - <4 total clocks  => no nibble on MOSI and MISO
          - clocks not multiple of 8 (except 4) => error
          - odd nibble count (>1) for MOSI/MISO => error
        """
        items = []
        nm = len(self.mosi_nibbles)
        ni = len(self.miso_nibbles)

        # clocks estimated from the maximum between MOSI/MISO (each nibble ~ 4 clocks)
        total_nibbles_est = max(nm, ni)
        total_bits_est = total_nibbles_est * 4

        if total_nibbles_est == 0:
            items.append({
                'dir': 'BUS',
                'kind': 'error',
                'val': None,
                'key_time': cs_start,
                'msg': 'No data in CS: < 4 clocks (no nibble on MOSI/MISO)'
            })
        else:
            # not a multiple of 8 (except 4)
            if not (total_bits_est == 4 or (total_bits_est % 8 == 0)):
                items.append({
                    'dir': 'BUS',
                    'kind': 'error',
                    'val': None,
                    'key_time': cs_start,
                    'msg': f'Estimated clocks = {total_bits_est} (not multiple of 8 and != 4)'
                })

        # odd (>1) on MOSI
        if nm > 1 and (nm % 2) == 1:
            items.append({
                'dir': 'MOSI',
                'kind': 'error',
                'val': None,
                'key_time': cs_start,
                'msg': f'MOSI nibble count = {nm} (odd > 1)'
            })

        # odd (>1) on MISO
        if ni > 1 and (ni % 2) == 1:
            items.append({
                'dir': 'MISO',
                'kind': 'error',
                'val': None,
                'key_time': cs_start,
                'msg': f'MISO nibble count = {ni} (odd > 1)'
            })

        return items

    def _flush_cs(self, end_time):
        """
        End of CS cycle: generate frames with strictly increasing begin.
        Distribute begin times in the interval (cs_start, end_time).
        """
        cs_start = self.cs_start

        # 1) Build items: first possible errors, then MOSI/MISO data
        items = []
        items.extend(self._build_error_items(cs_start, end_time))
        items.extend(self._build_items_for_dir('MOSI', self.mosi_nibbles))
        items.extend(self._build_items_for_dir('MISO', self.miso_nibbles))

        # reset state before creating final frames
        self._reset_cs_state()

        if not items:
            return []

        # 2) Sort by key_time (with errors at the beginning because key_time=cs_start)
        items.sort(key=lambda it: it['key_time'])

        # 3) Assign monotonic times
        total = len(items)
        span = end_time - cs_start           # SaleaeTimeDelta
        # Avoid edges: (total+2) slots
        step = span / float(total + 2)       # SaleaeTimeDelta
        frames = []
        for i, it in enumerate(items, start=1):
            begin = cs_start + (step * float(i))
            finish = begin + (step * float(0.9))
            if finish > end_time:
                finish = end_time

            kind = it['kind']
            if kind == 'byte_ok':
                frames.append(AnalyzerFrame('byte_ok', begin, finish, {
                    'dir': it['dir'], 'val': '0x%02X' % (it['val'] & 0xFF)
                }))
            elif kind == 'nibble_ok':
                frames.append(AnalyzerFrame('nibble_ok', begin, finish, {
                    'dir': it['dir'], 'val': '0x%X' % (it['val'] & 0xF)
                }))
            else:  # 'error'
                frames.append(AnalyzerFrame('error', begin, finish, {
                    'msg': it.get('msg', 'Detected anomaly')
                }))

        return frames

    # ---------- HLA API ----------
    def decode(self, frame: AnalyzerFrame):
        # CS delimitation (depends on SPI LLA)
        if frame.type == 'enable':
            self.cs_active = True
            self.cs_start = frame.start_time
            return AnalyzerFrame('packet', frame.start_time, frame.end_time, {'dir': 'CS', 'info': 'enable'})

        if frame.type == 'disable':
            # End of CS cycle: produce frames and then the 'disable' marker
            out = self._flush_cs(frame.end_time)
            out.append(AnalyzerFrame('packet', frame.start_time, frame.end_time, {'dir': 'CS', 'info': 'disable'}))
            return out

        if frame.type != 'result':
            return None

        # In some setups the LLA does not emit enable/disable
        if not self.cs_active:
            self.cs_active = True
            self.cs_start = frame.start_time

        # In 4-bit mode, mosi/miso are sequences of values 0..15
        mosi = frame.data.get('mosi')
        miso = frame.data.get('miso')

        if isinstance(mosi, (bytes, bytearray, list, tuple)):
            for n in mosi:
                self.mosi_nibbles.append((int(n) & 0xF, frame.start_time, frame.end_time))

        if isinstance(miso, (bytes, bytearray, list, tuple)):
            for n in miso:
                self.miso_nibbles.append((int(n) & 0xF, frame.start_time, frame.end_time))

        # During 'result' we accumulate; no immediate output
        return None
