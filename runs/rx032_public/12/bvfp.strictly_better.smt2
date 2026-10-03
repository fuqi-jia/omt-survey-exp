; benchmark generated from python API
(set-info :status unknown)
(declare-fun a () (_ FloatingPoint 8 24))
(declare-fun b () (_ FloatingPoint 8 24))
(assert
 (or (fp.isNormal a) (fp.isZero a) (fp.isSubnormal a)))
(assert
 (or (fp.isNormal b) (fp.isZero b) (fp.isSubnormal b)))
(assert
 (let ((?x11 ((_ to_fp 8 24) (_ bv0 32))))
 (fp.gt a ?x11)))
(assert
 (let ((?x11 ((_ to_fp 8 24) (_ bv0 32))))
 (fp.gt b ?x11)))
(assert
 (not (fp.gt (fp.mul roundNearestTiesToEven a b) ((_ to_fp 8 24) (_ bv0 32)))))
(assert
 (let ((?x29 (fp.to_ieee_bv a)))
(let ((?x33 (bvnot ?x29)))
(let ((?x30 ((_ extract 31 31) ?x29)))
(let (($x32 (= ?x30 (_ bv1 1))))
(let ((?x36 (ite $x32 ?x33 (bvxor ?x29 (_ bv2147483648 32)))))
(let (($x40 (not (fp.isNaN a))))
(and $x40 (bvugt ?x36 (_ bv3204448256 32))))))))))
(check-sat)
