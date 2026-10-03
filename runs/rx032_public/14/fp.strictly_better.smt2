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
 (let ((?x54 (fp (_ bv0 1) (_ bv0 8) (_ bv1 23))))
(fp.lt right ?x54)))
(check-sat)
