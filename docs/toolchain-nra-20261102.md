# IPOPT 3.14.20 与 Couenne 0.5.9

正式版本来源：

- [Ipopt releases](https://github.com/coin-or/Ipopt/releases/tag/releases%2F3.14.20)
- [Couenne 0.5.9](https://github.com/coin-or/Couenne/tree/releases/0.5.9)，
  `fb930178e08e275c9a7908cbb32c90996dfa1a04`
- [Bonmin 1.8.9](https://github.com/coin-or/Bonmin/tree/releases/1.8.9)，
  `030d111af16a0f30b6fff851ba7f983bea14f982`

实际包清单见 `runs/nra_public_20261102/conda-environment.json`。
IPOPT 3.14.20、CBC 2.10.13、ASL、MUMPS 5.8.2 及编译器来自 conda-forge。
Bonmin 和 Couenne 使用上述发行源码，链接到同一套依赖；未修改求解算法。

```bash
micromamba create -y -p /tmp/gomt-nlp-20261102 -c conda-forge \
  ipopt=3.14.20 coin-or-cbc=2.10.13 pkg-config gfortran_linux-64

export PKG_CONFIG_PATH=/tmp/gomt-nlp-20261102/lib/pkgconfig
export LD_LIBRARY_PATH=/tmp/gomt-nlp-20261102/lib
export PATH=/tmp/gomt-nlp-20261102/bin:$PATH
export F77=/tmp/gomt-nlp-20261102/bin/x86_64-conda-linux-gnu-gfortran
export FLIBS='-L/tmp/gomt-nlp-20261102/lib -lgfortran -lquadmath -lm'
export CXX='g++ -I/tmp/gomt-nlp-20261102/include/asl'
export LIBS='-L/tmp/gomt-nlp-20261102/lib -lipoptamplinterface -lasl -lCgl -lCoinUtils'
```

先在 Bonmin 1.8.9 源码根目录执行，再在 Couenne 0.5.9 源码根目录执行：

```bash
./configure --prefix=/tmp/gomt-nlp-20261102 \
  --with-asl-lib='-L/tmp/gomt-nlp-20261102/lib -lasl' \
  --with-asl-incdir=/tmp/gomt-nlp-20261102/include/asl \
  --disable-dependency-tracking
make -j8
make install
```

当前 Ipopt 将 AMPL 接口放在独立的 `libipoptamplinterface` 中，需显式链接。
上述 ASL 参数使 Couenne 的 NL 入口启用。动态库搜索路径必须覆盖依赖目录。

```bash
/tmp/gomt-nlp-20261102/bin/ipopt -v
/tmp/gomt-nlp-20261102/bin/couenne -v
```

Couenne 的 AMPL 选项为 `bonmin.time_limit`、`bonmin.allowable_gap` 和
`bonmin.allowable_fraction_gap`，与其命令行 `couenne -=` 所列名称一致。
正式调用均使用 `120`、`1e-8`、`1e-8`。Gurobi 析取编码的 QCP 收敛容差为
`BarQCPConvTol=1e-8`；正式批次对全部九例采用相同设置。

所有实际二进制、动态库及运行脚本的 SHA-256 见
`runs/nra_public_20261102/toolchain.json`。正式数据审计和来源记录见
`DATA_PROVENANCE.md`、`REPRODUCE_20261102.md`。
