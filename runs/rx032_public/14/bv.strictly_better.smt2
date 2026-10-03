; benchmark generated from python API
(set-info :status unknown)
(declare-fun left () (_ FloatingPoint 8 24))
(declare-fun right () (_ FloatingPoint 8 24))
(assert
 (or (fp.isNormal left) (fp.isSubnormal left) (fp.isZero left)))
(assert
 (or (fp.isNormal right) (fp.isSubnormal right) (fp.isZero right)))
(assert
 (fp.geq left (_ +zero 8 24)))
(assert
 (fp.geq right (_ +zero 8 24)))
(assert
 (let ((?x28 (fp.div roundNearestTiesToEven left right)))
 (let ((?x11 ((_ to_fp 8 24) (_ bv2139095039 32))))
 (let ((?x32 (ite (fp.lt right (fp.div roundNearestTiesToEven left ?x11)) ?x11 ?x28)))
 (let (($x29 (fp.eq right (_ +zero 8 24))))
 (let ((?x33 (ite $x29 ?x11 ?x32)))
 (let ((?x35 (ite (fp.lt right ((_ to_fp 8 24) (_ bv1065353216 32))) ?x33 ?x28)))
 (not (or (fp.isNormal ?x35) (fp.isSubnormal ?x35) (fp.isZero ?x35))))))))))
(assert
 (let ((?x42 (fp.to_ieee_bv right)))
(let ((?x46 (bvnot ?x42)))
(let ((?x43 ((_ extract 31 31) ?x42)))
(let (($x45 (= ?x43 (_ bv1 1))))
(let ((?x49 (ite $x45 ?x46 (bvxor ?x42 (_ bv2147483648 32)))))
(let (($x53 (not (fp.isNaN right))))
(and $x53 (bvult ?x49 (_ bv2147483649 32))))))))))
(check-sat)
