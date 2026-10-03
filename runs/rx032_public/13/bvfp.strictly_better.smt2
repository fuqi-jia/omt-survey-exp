; benchmark generated from python API
(set-info :status unknown)
(declare-fun a () (_ FloatingPoint 8 24))
(declare-fun b () (_ FloatingPoint 8 24))
(declare-fun c () (_ FloatingPoint 8 24))
(assert
 (or (fp.isZero a) (fp.isNormal a) (fp.isSubnormal a)))
(assert
 (or (fp.isZero b) (fp.isNormal b) (fp.isSubnormal b)))
(assert
 (or (fp.isZero c) (fp.isNormal c) (fp.isSubnormal c)))
(assert
 (or (fp.isZero (fp.mul roundNearestTiesToEven a b)) (fp.isNormal (fp.mul roundNearestTiesToEven a b)) (fp.isSubnormal (fp.mul roundNearestTiesToEven a b))))
(assert
 (or (fp.isZero (fp.mul roundNearestTiesToEven b c)) (fp.isNormal (fp.mul roundNearestTiesToEven b c)) (fp.isSubnormal (fp.mul roundNearestTiesToEven b c))))
(assert
 (let ((?x31 (fp.mul roundNearestTiesToEven b c)))
 (let ((?x36 (fp.mul roundNearestTiesToEven a ?x31)))
 (or (fp.isZero ?x36) (fp.isNormal ?x36) (fp.isSubnormal ?x36)))))
(assert
 (let ((?x26 (fp.mul roundNearestTiesToEven a b)))
 (let ((?x41 (fp.mul roundNearestTiesToEven ?x26 c)))
 (or (fp.isZero ?x41) (fp.isNormal ?x41) (fp.isSubnormal ?x41)))))
(assert
 (let ((?x26 (fp.mul roundNearestTiesToEven a b)))
 (let ((?x41 (fp.mul roundNearestTiesToEven ?x26 c)))
 (let ((?x31 (fp.mul roundNearestTiesToEven b c)))
 (let ((?x36 (fp.mul roundNearestTiesToEven a ?x31)))
 (not (fp.eq ?x36 ?x41)))))))
(assert
 (let ((?x49 (fp.to_ieee_bv a)))
(let ((?x53 (bvnot ?x49)))
(let ((?x50 ((_ extract 31 31) ?x49)))
(let (($x52 (= ?x50 (_ bv1 1))))
(let ((?x56 (ite $x52 ?x53 (bvxor ?x49 (_ bv2147483648 32)))))
(let (($x60 (not (fp.isNaN a))))
(and $x60 (bvugt ?x56 (_ bv4286578687 32))))))))))
(check-sat)
