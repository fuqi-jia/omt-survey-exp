; benchmark generated from python API
(set-info :status unknown)
(declare-fun x () (_ FloatingPoint 11 53))
(declare-fun r () (_ FloatingPoint 11 53))
(assert
 (= x (fp (_ bv1 1) (_ bv1397 11) (_ bv3746490461901976 52))))
(assert
 (= (fp.abs x) r))
(assert
 (let ((?x15 (fp.to_ieee_bv r)))
(let ((?x18 (bvnot ?x15)))
(let ((?x16 ((_ extract 63 63) ?x15)))
(let (($x17 (= ?x16 (_ bv1 1))))
(let ((?x21 (ite $x17 ?x18 (bvxor ?x15 (_ bv9223372036854775808 64)))))
(let (($x25 (not (fp.isNaN r))))
(and $x25 (bvult ?x21 (_ bv15518647206753260696 64))))))))))
(check-sat)
