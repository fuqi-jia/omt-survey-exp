; benchmark generated from python API
(set-info :status unknown)
(declare-fun x () (_ FloatingPoint 11 53))
(declare-fun y () (_ FloatingPoint 11 53))
(declare-fun r () (_ FloatingPoint 11 53))
(assert
 (fp.geq x (fp (_ bv1 1) (_ bv818 11) (_ bv4237461149517505 52))))
(assert
 (fp.leq y (fp (_ bv0 1) (_ bv149 11) (_ bv2448250399680798 52))))
(assert
 (= (fp.sub roundTowardPositive x y) r))
(assert
 (let ((?x22 (fp.to_ieee_bv r)))
(let ((?x25 (bvnot ?x22)))
(let ((?x23 ((_ extract 63 63) ?x22)))
(let (($x24 (= ?x23 (_ bv1 1))))
(let ((?x28 (ite $x24 ?x25 (bvxor ?x22 (_ bv9223372036854775808 64)))))
(let (($x32 (not (fp.isNaN r))))
(and $x32 (= (_ bv5535190080516192574 64) ?x28)))))))))
(check-sat)
