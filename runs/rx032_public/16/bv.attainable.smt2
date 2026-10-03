; benchmark generated from python API
(set-info :status unknown)
(declare-fun x () (_ FloatingPoint 11 53))
(declare-fun y () (_ FloatingPoint 11 53))
(declare-fun r () (_ FloatingPoint 11 53))
(assert
 (fp.leq x (fp (_ bv1 1) (_ bv1694 11) (_ bv1639087830226334 52))))
(assert
 (fp.leq y (fp (_ bv0 1) (_ bv450 11) (_ bv3468604031872236 52))))
(assert
 (= (fp.add roundTowardZero x y) r))
(assert
 (let ((?x22 (fp.to_ieee_bv r)))
(let ((?x25 (bvnot ?x22)))
(let ((?x23 ((_ extract 63 63) ?x22)))
(let (($x24 (= ?x23 (_ bv1 1))))
(let ((?x28 (ite $x24 ?x25 (bvxor ?x22 (_ bv9223372036854775808 64)))))
(let (($x32 (not (fp.isNaN r))))
(and $x32 (= (_ bv1592635180258929250 64) ?x28)))))))))
(check-sat)
