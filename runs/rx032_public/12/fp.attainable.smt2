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
 (let ((?x41 (fp (_ bv0 1) (_ bv126 8) (_ bv0 23))))
(= a ?x41)))
(check-sat)
