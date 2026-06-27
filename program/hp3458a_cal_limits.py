"""HP 3458A Cal_RAM határérték-tábla.

Szerkeszthető — minden értéknek a firmware határain belül kell maradnia.
"""
CAL_LIMITS: dict[int, tuple[float, float]] = {
    0x0000: (39921.5, 40079.2),  # 40Kohm reference
    0x0008: (7.0, 7.5),  # 7Vdc reference
    0x0010: (-0.05, 0.05),  # dcv zero front 100mV
    0x0018: (-0.05, 0.05),  # dcv zero rear  100mV
    0x0020: (-0.005, 0.005),  # dcv zero front 1V
    0x0028: (-0.005, 0.005),  # dcv zero rear  1V
    0x0030: (-0.0005, 0.0005),  # dcv zero front 10V
    0x0038: (-0.0005, 0.0005),  # dcv zero rear  10V
    0x0040: (-0.0065, 0.0065),  # dcv zero front 100V
    0x0048: (-0.0065, 0.0065),  # dcv zero rear  100V
    0x0050: (-0.00065, 0.00065),  # dcv zero front 1KV
    0x0058: (-0.00065, 0.00065),  # dcv zero rear  1KV
    0x0060: (-33.5, 33.5),  # ohm zero front 10
    0x0068: (-3.3, 3.3),  # ohm zero front 100
    0x0070: (-0.33, 0.33),  # ohm zero front 1K
    0x0078: (-0.033, 0.033),  # ohm zero front 10K
    0x0080: (-0.0033, 0.0033),  # ohm zero front 100K
    0x0088: (-0.00085, 0.00085),  # ohm zero front 1M
    0x0090: (-0.00085, 0.00085),  # ohm zero front 10M
    0x0098: (-0.0085, 0.0085),  # ohm zero front 100M
    0x00A0: (-0.085, 0.085),  # ohm zero front 1G
    0x00A8: (-33.0, 33.0),  # ohm zero rear 10
    0x00B0: (-3.3, 3.3),  # ohm zero rear 100
    0x00B8: (-0.33, 0.33),  # ohm zero rear 1K
    0x00C0: (-0.033, 0.033),  # ohm zero rear 10K
    0x00C8: (-0.0033, 0.0033),  # ohm zero rear 100K
    0x00D0: (-0.00085, 0.00085),  # ohm zero rear 1M
    0x00D8: (-0.00085, 0.00085),  # ohm zero rear 10M
    0x00E0: (-0.0085, 0.0085),  # ohm zero rear 100M
    0x00E8: (-0.085, 0.085),  # ohm zero rear 1G
    0x00F0: (-0.33, 0.33),  # ohmf zero front 10
    0x00F8: (-0.033, 0.033),  # ohmf zero front 100
    0x0100: (-0.033, 0.033),  # ohmf zero front 1K
    0x0108: (-0.033, 0.033),  # ohmf zero front 10K
    0x0110: (-0.015, 0.015),  # ohmf zero front 100K
    0x0118: (-0.015, 0.015),  # ohmf zero front 1M
    0x0120: (-0.015, 0.015),  # ohmf zero front 10M
    0x0128: (-0.15, 0.15),  # ohmf zero front 100M
    0x0130: (-1.5, 1.5),  # ohmf zero front 1G
    0x0138: (-0.33, 0.33),  # ohmf zero rear 10
    0x0140: (-0.033, 0.033),  # ohmf zero rear 100
    0x0148: (-0.033, 0.033),  # ohmf zero rear 1K
    0x0150: (-0.033, 0.033),  # ohmf zero rear 10K
    0x0158: (-0.015, 0.015),  # ohmf zero rear 100K
    0x0160: (-0.015, 0.015),  # ohmf zero rear 1M
    0x0168: (-0.015, 0.015),  # ohmf zero rear 10M
    0x0170: (-0.15, 0.15),  # ohmf zero rear 100M
    0x0178: (-1.5, 1.5),  # ohmf zero rear 1G
    0x01A4: (-15.0, 90.0),  # cal 0 temperature
    0x01AC: (-15.0, 90.0),  # cal 10 temperature
    0x01B4: (-15.0, 90.0),  # cal 10k temperature
    0x01C0: (-1.8, 1.8),  # dci zero rear 100nA
    0x01C8: (-0.15, 0.15),  # dci zero rear 1uA
    0x01D0: (-0.05, 0.05),  # dci zero rear 10uA
    0x01D8: (-0.07, 0.074),  # dci zero rear 100uA
    0x01E0: (-0.1, 0.1),  # dci zero rear 1mA
    0x01E8: (-0.1, 0.1),  # dci zero rear 10mA
    0x01F0: (-0.01, 0.01),  # dci zero rear 100mA
    0x01F8: (-0.1, 0.1),  # dci zero rear 1A
    0x0200: (0.00028, 0.000314),  # dcv gain 100mV
    0x0208: (0.0028, 0.00314),  # dcv gain 1V
    0x0210: (0.029, 0.03085),  # dcv gain 10V
    0x0218: (0.28, 0.314),  # dcv gain 100V
    0x0220: (2.8, 3.14),  # dcv gain 1KV
    0x0228: (0.0291, 0.0305),  # ohm gain 10
    0x0230: (0.291, 0.305),  # ohm gain 100
    0x0238: (3.0, 3.05),  # ohm gain 1K
    0x0240: (30.0, 30.5),  # ohm gain 10K
    0x0248: (590.0, 615.0),  # ohm gain 100K
    0x0250: (5900.0, 6150.0),  # ohm gain 1M
    0x0258: (59000.0, 61500.0),  # ohm gain 10M
    0x0260: (59000.0, 61500.0),  # ohm gain 100M
    0x0268: (59000.0, 61500.0),  # ohm gain 1G
    0x0270: (0.0291, 0.0305),  # ohm ocomp gain 10
    0x0278: (0.291, 0.305),  # ohm ocomp gain 100
    0x0280: (3.0, 3.05),  # ohm ocomp gain 1K
    0x0288: (30.0, 30.5),  # ohm ocomp gain 10K
    0x0290: (590.0, 615.0),  # ohm ocomp gain 100K
    0x0298: (5900.0, 6150.0),  # ohm ocomp gain 1M
    0x02A0: (59000.0, 61500.0),  # ohm ocomp gain 10M
    0x02A8: (59000.0, 61500.0),  # ohm ocomp gain 100M
    0x02B0: (59000.0, 61500.0),  # ohm ocomp gain 1G
    0x02B8: (5.150000000000001e-09, 5.8e-09),  # dci gain 100nA
    0x02C0: (6.2500000000000005e-09, 6.8e-09),  # dci gain 1uA
    0x02C8: (5.255e-08, 6e-08),  # dci gain 10uA
    0x02D0: (3.7999999999999996e-07, 4.3e-07),  # dci gain 100uA
    0x02D8: (2.8e-06, 3.1e-06),  # dci gain 1mA
    0x02E0: (2.75e-05, 3.1e-05),  # dci gain 10mA
    0x02E8: (0.0025, 0.0029),  # dci gain 100mA
    0x02F0: (0.0255, 0.034),  # dci gain 1A
    0x02FA: (4.86, 5.14),  # high speed gain
    0x0302: (-1e-10, 5e-08),  # il
    0x030A: (-2e-10, 2e-10),  # il2
    0x0312: (9710000.0, 10290000.0),  # rin
    0x031A: (-1.0, 1.0),  # low aperture
    0x0322: (-1.0, 1.0),  # high aperture
    0x032A: (0.999, 1.001),  # high aperture slope .01 PLC
    0x0332: (0.999, 1.001),  # high aperture slope .1 PLC
    0x033A: (1666.5, 1667.9),  # high aperture null .01 PLC
    0x0342: (16666.5, 16667.9),  # high aperture null .1 PLC
    0x0442: (-15.0, 95.0),  # acal dcv temperature
    0x044A: (-15.0, 95.0),  # acal ohm temperature
    0x0452: (-15.0, 95.0),  # acal acv temperature
    0x0484: (-1799.0, -250.0),  # acdcv sync offset 10mV
    0x048C: (-1799.0, -250.0),  # acdcv sync offset 100mV
    0x0494: (-1799.0, -250.0),  # acdcv sync offset 1V
    0x049C: (-1799.0, -250.0),  # acdcv sync offset 10V
    0x04A4: (-1799.0, -250.0),  # acdcv sync offset 100V
    0x04AC: (-1799.0, -250.0),  # acdcv sync offset 1KV
    0x04B4: (-1799.0, -250.0),  # acv sync offset 10mV
    0x04BC: (-1799.0, -250.0),  # acv sync offset 100mV
    0x04C4: (-1799.0, -250.0),  # acv sync offset 1V
    0x04CC: (-1799.0, -250.0),  # acv sync offset 10V
    0x04D4: (-1799.0, -250.0),  # acv sync offset 100V
    0x04DC: (-1799.0, -250.0),  # acv sync offset 1KV
    0x04E4: (1.51e-06, 2.3e-06),  # acv sync gain 10mV
    0x04EC: (1.56e-05, 2.3e-05),  # acv sync gain 100mV
    0x04F4: (0.000156, 0.00023),  # acv sync gain 1V
    0x04FC: (0.00156, 0.0023),  # acv sync gain 10V
    0x0504: (0.0156, 0.023),  # acv sync gain 100V
    0x050C: (0.156, 0.23),  # acv sync gain 1KV
    0x0514: (-2840000.0, 2830000.0),  # ab ratio
    0x051C: (9.5, 11.0),  # gain ratio
    0x0524: (2.5253080985915528e-05, 3.41e-05),  # acv ana gain 10mV
    0x052C: (0.00026, 0.00035),  # acv ana gain 100mV
    0x0534: (0.0026, 0.0035),  # acv ana gain 1V
    0x053C: (0.026, 0.035),  # acv ana gain 10V
    0x0544: (0.26, 0.35),  # acv ana gain 100V
    0x054C: (2.6, 3.5),  # acv ana gain 1KV
    0x0554: (-1.5, 1.5),  # acv ana offset 10mV
    0x055C: (-1.5, 1.5),  # acv ana offset 100mV
    0x0564: (-1.5, 1.5),  # acv ana offset 1V
    0x056C: (-1.5, 1.5),  # acv ana offset 10V
    0x0574: (-1.5, 1.5),  # acv ana offset 100V
    0x057C: (-1.5, 1.5),  # acv ana offset 1KV
    0x0584: (0.99, 1.05),  # rmsdc ratio
    0x058C: (0.999, 1.001),  # sampdc ratio
    0x0594: (0.995, 1.005),  # aci gain
    0x059E: (0.0, 10.0),  # Cal_59e
    0x05A6: (0.0, 10.0),  # Cal_5a6
    0x05AE: (0.0, 10.0),  # Cal_5ae
    0x05B6: (0.9999, 1.0001),  # freq gain
}
