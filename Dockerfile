FROM alpine:latest

# Get required packages
RUN apk add --update --no-cache wget autoconf automake openssl libtool libffi-dev python3 npm make g++ git openssl-dev python3-dev

# build the libsecp256k1 library
RUN git clone https://github.com/bitcoin-core/secp256k1.git
RUN cd secp256k1 && ./autogen.sh && ./configure && make && make install

RUN pip3 install --upgrade pip

# Install the Python requirements
COPY tests/requirements.txt /
RUN pip3 install -r requirements.txt

# Install Ganache
RUN npm install -g ganache-cli

# Copy the contract source code and test suite
COPY ./code /code
COPY ./tests /tests

# Set the working directory to the tests/ dir
WORKDIR /tests

# Create a script for running Ganache and then running the tests (need to sleep to ensure Ganache has initialised)
RUN echo "brownie test -v" > run-tests.sh
RUN chmod u+x run-tests.sh

# "docker run" will execute the tests against the compiled contracts
CMD ./run-tests.sh
