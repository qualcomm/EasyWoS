#!/bin/bash

path2=$(dirname $0)
echo $path2

mkdir -p $path2/porting_code/db $path2/porting_code/advisor/templates

cp $path2/cpp_scanner.py $path2/porting_code/

cp $path2/__init__.py $path2/porting_code/

python3 $path2/db/crypto_file.py

rm -f $path2/db/crypto_file.py $path2/db/check_points.yaml

cp -r $path2/db $path2/porting_code/

cp -r $path2/advisor/templates $path2/porting_code/advisor/

cd $path2/advisor

cp ./__init__.py ../porting_code/advisor/

python3 setup.py

find ./build/cpp/advisor -name '*__init__*' -exec rm -rf {} \;

cp ./build/cpp/advisor/* ../porting_code/advisor/

rm -rf ./tmp

rm -rf ./build

find . -name '*.c' -exec rm -rf {} \;

# find . -name '*.py' |  grep  -v  '__init__.py' | xargs rm