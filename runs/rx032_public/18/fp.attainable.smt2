; benchmark generated from python API
(set-info :status unknown)
(declare-fun x () (_ FloatingPoint 11 53))
(declare-fun y () (_ FloatingPoint 11 53))
(declare-fun r () (_ FloatingPoint 11 53))
(assert
 (let ((?x9 (fp (_ bv1 1) (_ bv818 11) (_ bv4237461149517505 52))))
 (fp.geq x ?x9)))
(assert
 (fp.leq y (fp (_ bv0 1) (_ bv149 11) (_ bv2448250399680798 52))))
(assert
 (= (fp.sub roundTowardPositive x y) r))
(assert
 (let ((?x9 (fp (_ bv1 1) (_ bv818 11) (_ bv4237461149517505 52))))
(= r ?x9)))
(check-sat)
