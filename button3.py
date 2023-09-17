from machine import Pin, Signal, PWM
import time


class KeyList():
    ''' (key, value) のリストを制御する '''
    def __init__(self):
        self._klist: list[tuple[object, object]] = []

    def _findkey(self, key) -> int:
        ''' keyに合致するデータのインデックスを返す。存在しなければ -1 を返す '''
        for i in range(len(self._klist)):
            if self._klist[i][0] == key:
                return i
        return -1

    def __setitem__(self, key, value):
        i = self._findkey(key)
        if i != -1:
            self._klist[i] = (key, value)
        else:
            self._klist.append((key, value))

    def __getitem__(self, key):
        i = self._findkey(key)
        if i != -1:
            return self._klist[i][1]
        return None

    def keys(self):
        return [item[0] for item in self._klist]

    def values(self):
        return [item[1] for item in self._klist]


class Button():
    ''' 押しボタンクラス '''

    # (指定されたPin, 生成されたボタンinstance) のリスト
    _kroster = KeyList()

    def __init__(self, _pin,                # 登録した Pin
                 name: str | None = None,   # 登録する Pinの名前（任意）
                 invert=False,              # 押してLowならTrue
                 bouncetime=100,            # チャタリング防止時間(ms)
                 function=None,             # ボタンが押された時のファンクション
                 args=None,                 # ファンクションの位置引数
                 kwargs=None,               # ファンクションのキーワード引数
                 ) -> None:
        print(_pin)
        self._pin = _pin                # 登録した Pin
        self._invert = invert           # ボタンがGND接続のとき、Trueを指定
        self._signal = Signal(_pin, invert=self._invert)

        # ボタンの名前を取得（引数で省略なら"GPIOxx"を設定）
        self._name = name if name else Button._get_name(self._pin)

        self._time_ticks = 0            # チャタリング防止用 time_ticks
        self._dtime = bouncetime        # チャタリング防止時間(ms)

        self._count = 0                 # 押された回数
        self._function = function       # ボタンが押された時のファンクション
        self._fargs = args              # ファンクションの位置引数
        self._fkwargs = kwargs          # ファンクションのキーワード引数

        # 生成されたinstanceと指定されたPinを内部のリストに登録
        self._put_myself(self._pin)

        # 割り込みハンドラーを設定（ボタンが押された時）
        if self._invert:
            self._pin.irq(trigger=Pin.IRQ_FALLING, handler=Button._handler)
        else:
            self._pin.irq(trigger=Pin.IRQ_RISING, handler=Button._handler)

    @staticmethod
    def _handler(pin):
        ''' ボタンが押された時の割り込みハンドラー '''
        _flag = pin.irq().flags()
        print(f"  (0x{_flag:02x})")

        myself = Button._get_myself(pin)    # 割り込み対象の自object（myself）を取得
        if not myself:      # 自分的に存在しないボタンの場合は無視
            return
        # チャタリング防止のため制限時間内の再割り込みは無視
        if time.ticks_diff(time.ticks_ms(), myself._time_ticks) < myself._dtime:
            return
        # ゴースト除去。多分ボタンリリース時のチャタリング
        if not myself._signal.value():
            print(f"push rejected!! for {myself._name}")
            return

        ''' これ以降が、ボタンが押された場合の処理 '''
        print(f"@@@@_PUSHED!! ({_flag:02x}) {myself.get_name()}")
        myself._count += 1

        # 登録されたファンクションを実行
        if myself._function:
            myself._do_function(myself._function, myself._fargs, myself._fkwargs)

        myself._time_ticks = time.ticks_ms()

    @staticmethod
    def _get_name(pin: Pin) -> str:
        ''' Pinに設定されている名前（GPIOxx）を取得する '''
        return repr(pin).split("(")[1].split(",")[0]

    @classmethod
    def _get_myself(cls, _pin):
        ''' 内部リストから、_pinに該当するボタンのinstance(myself)を取得する '''
        return cls._kroster[_pin]

    def _put_myself(self, _pin):
        ''' 内部リストに、生成されたinstance(self)と指定されたPinを登録する '''
        # _pin重複チェック。重複していたら古いinstanceは削除
        btn = Button._kroster[_pin]
        if btn:
            del btn
        Button._kroster[_pin] = self

    def _exist_myself(self) -> bool:
        ''' ボタンinstanceが生きているかのチェック '''
        return self in self._kroster.values()

    def _do_function(self, function, fargs, fkwargs):
        ''' ボタンに対して、登録された function を実行する '''
        if fargs is not None:           # 位置引数あり
            if not isinstance(fargs, tuple):    # tupleでなければ tuple化
                fargs = (fargs, )
            if fkwargs:                      # 位置引数とキーワード引数あり
                function(*fargs, **fkwargs, myself=self)
            else:                           # 位置引数のみ
                function(*fargs, myself=self)
        elif fkwargs:                    # キーワード引数あり
            function(**fkwargs, myself=self)
        else:                           # 引数なし
            function(myself=self)

    def set_function(self, function=None, args=None, kwargs=None):
        ''' ボタンが押された時の動作を登録する '''
        assert self._exist_myself(), f"{self} is expired!"
        self._function = function
        self._fargs = args
        self._fkwargs = kwargs

    def get_count(self) -> int:
        ''' ボタンが押された回数を返す '''
        return self._count

    def reset_count(self):
        ''' ボタンが押された回数をリセットする '''
        self._count = 0

    def get_name(self):
        ''' ボタンに設定した名前を返す '''
        return self._name

    def get_signal(self):
        ''' ボタンに設定したpinの状態（signal）を返す '''
        return self._signal()


class Volume():
    ''' PWMデバイスのボリュームを操作する '''
    def __init__(self, pwm: PWM,        # PWMデバイス
                 min: int = 0,          # ボリュームの最小値
                 max: int = 10,         # ボリュームの最大値
                 initial: int = 0,      # ボリュームの初期値
                 freq: int = 120,       # PWMの周波数
                 curve: str | int | float = 'B',    # ボリュームのカーブ
                 invert: bool = False   # 反転（出力Lで点灯の場合、True）
                 ):
        self._pwm = pwm
        self._min = min
        self._max = max
        self._range = max - min
        self._vol = initial
        self._invert = invert

        if type(curve) is int or type(curve) is float:
            self._exp: int | float = curve
        else:
            assert curve in list('ABCD'),\
                "The value of the argument 'curve' must be one of the following:"\
                " 'A','B','C','D' or numeric"
            self._exp = {'A': 2, 'B': 1, 'C': 0.7, 'D': 3}.get(curve)

        pwm.freq(freq)
        pwm.duty_u16(self.u16value(min))

    def u16value(self, value) -> int:
        reg = value ** self._exp / self._range ** self._exp
        reg = (1 - reg) if self._invert else reg
        return int(65535 * reg)

    def up(self, opposite=None, myself=None) -> int:
        ''' ボリュームを一段上げる '''
        self._vol = min(self._vol + 1, self._max)
        if opposite.get_signal():   # 対向のボタンも（同時に）押されてた
            self._vol = self._min
        self._pwm.duty_u16(self.u16value(self._vol))
        return self._vol

    def down(self, myself=None, opposite=None) -> int:
        ''' ボリュームを一段下げる '''
        self._vol = max(self._vol - 1, self._min)
        if opposite.get_signal():   # 対向のボタンも（同時に）押されてた
            self._vol = self._min
        self._pwm.duty_u16(self.u16value(self._vol))
        return self._vol

    def get_value(self) -> int:
        ''' 現在のボリューム値を返す '''
        return self._vol


class OnOff_Switch():
    ''' 入り切りスイッチ '''
    def __init__(self, device):
        self._device = device
        self._on_off = False

    def on(self, myself):
        self._device.on()
        self._on_off = True

    def off(self, myself):
        self._device.off()
        self._on_off = False


class Toggle():
    ''' トグルスイッチ '''
    def __init__(self, device):
        self._device = device
        self._on_off = False
        self._device.value(self._on_off)

    def toggle(self, myself=None):
        print(f"toggle {myself.get_name()} count={myself.get_count()}")
        self._on_off = False if self._on_off else True
        self._device.value(self._on_off)


# スイッチ用 pin定義
# スイッチを 3.3Vと接続する時は、GPIO側をPULL_DOWN、押すとH入力
# スイッチをGNDと接続するときは、GPIO側をPULL_UP、押すとL入力（invert）

# LED用 pin定義
# GPIOにアノード側を接続するときは、出力Hで点灯
# GPIOにカソード側を接続するときは、出力Lで点灯（invert）

# [物理]設定
pin11 = Pin(11, Pin.IN, Pin.PULL_UP)            # 赤LED用押しボタン
ledR = Signal(Pin(18, Pin.OUT, value=0))        # 赤LED

# [論理]設定
ledR_toggle = Toggle(ledR)                      # 赤LED用トグルスイッチを定義
# 赤LED用押しボタンに、トグルスイッチを接続
btn0 = Button(pin11, function=ledR_toggle.toggle, invert=True, bouncetime=200)


# [物理]設定
pin12 = Pin(12, Pin.IN, Pin.PULL_DOWN)          # 緑LED用押しボタン（切り）
pin13 = Pin(13, Pin.IN, Pin.PULL_DOWN)          # 緑LED用押しボタン（入り）
ledG = Pin(17, Pin.OUT, value=0)                # 緑LED

# [論理]設定
ledG_switch = OnOff_Switch(ledG)                # 緑LED用入り切りスイッチを定義
# 緑LED用押しボタンに、「切り」スイッチ、「入り」スイッチを接続
btnG_off = Button(pin12, name="G_off", function=ledG_switch.off, bouncetime=200)
btnG_on = Button(pin13, name="G_on", function=ledG_switch.on, bouncetime=200)


# [物理]設定
pin14 = Pin(14, Pin.IN, Pin.PULL_UP)            # 黄LED用押しボタン（down）
pin15 = Pin(15, Pin.IN, Pin.PULL_UP)            # 黄LED用押しボタン（up）
ledY = Pin(16, Pin.OUT, value=1)                # 黄LED

# [論理]設定
# 黄LED用照度up/downボタンを定義
ledY_vol = Volume(PWM(ledY), min=0, max=10, curve='A')
# 黄LED用押しボタンdown、upを接続
btnY_down = Button(pin14, name="Y_down", invert=True, bouncetime=200)
btnY_up = Button(pin15, name="Y_up", invert=True, bouncetime=200)
# 黄LED用押しボタンdown、upにボリュームdown、ボリュームup機能を設定
btnY_down.set_function(ledY_vol.down, kwargs={'opposite': btnY_up})
btnY_up.set_function(ledY_vol.up, (), {'opposite': btnY_down})

while True:
    '''
    ここにいろいろ、メイン処理を書く
    '''
    pass
