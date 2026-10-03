; benchmark generated from python API
(set-info :status unknown)
(declare-fun x () (_ FloatingPoint 11 53))
(declare-fun r () (_ FloatingPoint 11 53))
(assert
 (fp.leq x (fp (_ bv0 1) (_ bv1295 11) (_ bv1738192835460489 52))))
(assert
 (= (fp.sqrt roundTowardZero x) r))
(assert
 (let ((?x27 (fp (_ bv0 1) (_ bv1159 11) (_ bv798337208327341 52))))
(= r ?x27)))
(check-sat)
