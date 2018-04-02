from ethereum.tools import tester
from ethereum import utils
from ethereum.tools._solidity import get_solidity
SOLIDITY_AVAILABLE = get_solidity() is not None
from Crypto.Hash import SHA256

import bitcoin

# Logging
from ethereum import slogging
slogging.configure(':INFO,eth.vm:INFO')
#slogging.configure(':DEBUG')
#slogging.configure(':DEBUG,eth.vm:TRACE')

xor = lambda (x,y): chr(ord(x) ^ ord(y))
xors = lambda x,y: ''.join(map(xor,zip(x,y)))
zfill = lambda s: (32-len(s))*'\x00' + s
flatten = lambda x: [z for y in x for z in y]

def int_to_bytes(x):
    # pyethereum int to bytes does not handle negative numbers
    assert -(1<<255) <= x < (1<<255)
    return utils.int_to_bytes((1<<256) + x if x < 0 else x)

def broadcast(p, r, h, sig):
    print 'player[%d]'%p.i, 'broadcasts', r, h.encode('hex'), sig

def sign(h, priv):
    assert len(h) == 32
    V, R, S = bitcoin.ecdsa_raw_sign(h, priv)
    return V,R,S

def verify_signature(addr, h, (V,R,S)):
    pub = bitcoin.ecdsa_raw_recover(h, (V,R,S))
    pub = bitcoin.encode_pubkey(pub, 'bin')
    addr_ = utils.sha3(pub[1:])[12:]
    assert addr_ == addr
    return True

def getstatus():
    depositsL = contract.deposits(0)
    depositsR = contract.deposits(1)
    creditsL = contract.credits(0)
    creditsR = contract.credits(1)
    wdrawL = contract.withdrawals(0)
    wdrawR = contract.withdrawals(1)
    print 'Status:', ['OK','PENDING'][contract.status()]
    print '[L] deposits:', depositsL, 'credits:', creditsL, 'withdrawals:', wdrawL
    print '[R] deposits:', depositsR, 'credits:', creditsR, 'withdrawals:', wdrawR


class Player():
    def __init__(self, sk, i, contract):
        self.sk = sk
        self.i = i
        self.contract = contract
        self.status = "OK"
        self.lastRound = -1
        self.lastCommit = None, (0, 0, 0, 0)
        self.lastProposed = None

    def deposit(self, amt):
        self.contract.deposit(value=amt, sender=self.sk)

    def acceptInputs(self, r, payL, payR, wdrawL, wdrawR):
        assert self.status == "OK"
        assert r == self.lastRound + 1
        # Assumption - don't call acceptInputs(r,...) multiple times

        depositsL    = contract.deposits(0);
        depositsR    = contract.deposits(1);
        withdrawalsL = contract.withdrawals(0);
        withdrawalsR = contract.withdrawals(1);

        _, (creditsL, creditsR, withdrawnL, withdrawnR) = self.lastCommit

	assert payL <= depositsL + creditsL
	assert payR <= depositsR + creditsR
	assert wdrawL <= depositsL + creditsL - payL
	assert wdrawR <= depositsR + creditsR - payR

	creditsL += payR - payL - wdrawL
	creditsR += payL - payR - wdrawR
        withdrawalsL += wdrawL
        withdrawalsR += wdrawR

        self.lastProposed = (creditsL, creditsR, withdrawalsL, withdrawalsR)

        self.h = utils.sha3(zfill(utils.int_to_bytes(r)) +
                            zfill(int_to_bytes(creditsL)) +
                            zfill(int_to_bytes(creditsR)) +
                            zfill(utils.int_to_bytes(withdrawalsL)) +
                            zfill(utils.int_to_bytes(withdrawalsR)))
        sig = sign(self.h, self.sk)
        broadcast(self, r, self.h, sig)
        return sig

    def receiveSignatures(self, r, sigs):
        assert self.status == "OK"
        assert r == self.lastRound + 1

        for i,sig in enumerate(sigs):
            verify_signature(addrs[i], self.h, sig)

        self.lastCommit = sigs, self.lastProposed
        self.lastRound += 1

    def getstatus(self):
        print '[Local view of Player %d]' % self.i
        print 'Last round:', self.lastRound
        depositsL = contract.deposits(0)
        depositsR = contract.deposits(1)
        _, (creditsL, creditsR, wdrawL, wdrawR) = self.lastCommit
        print 'Status:', self.status
        print '[L] deposits:', depositsL, 'credits:', creditsL, 'withdrawals:', wdrawL
        print '[R] deposits:', depositsR, 'credits:', creditsR, 'withdrawals:', wdrawR


    def update(self):
        # Place our updated state in the contract
        sigs, (creditsL, creditsR, withdrawalsL, withdrawalsR) = self.lastCommit
        sig = sigs[1] if self.i == 0 else sigs[0]
        self.contract.update(sig, self.lastRound, (creditsL, creditsR), (withdrawalsL, withdrawalsR), sender=self.sk)


# Create the simulated blockchain
s = tester.Chain()
s.mine()
tester.gas_limit = 3141592


keys = [tester.k1,
        tester.k2]
addrs = map(utils.privtoaddr, keys)

# Create the contract
contract_code = open('contractPay.sol').read()
contract = s.contract(
    sourcecode=contract_code,
    language='solidity',
    args= ((addrs[0], addrs[1]),) )


def completeRound(players, r, payL, payR, wdrawL, wdrawR):
    sigL = players[0].acceptInputs(r, payL, payR, wdrawL, wdrawR)
    sigR = players[1].acceptInputs(r, payL, payR, wdrawL, wdrawR)
    sigs = (sigL, sigR)
    players[0].receiveSignatures(r, sigs)
    players[1].receiveSignatures(r, sigs)

# Take a snapshot before trying out test cases
#try: s.revert(s.snapshot())
#except: pass # FIXME: I HAVE NO IDEA WHY THIS IS REQUIRED
s.mine()
base = s.snapshot()

players = [Player(sk, i, contract) for i,sk in enumerate(keys)]

def test1():
    # Some test behaviors
    getstatus()
    players[0].deposit(10)
    getstatus()
    completeRound(players, 0, 5, 0, 0, 0)

    # Update
    players[0].getstatus()
    players[0].update()
    getstatus()

    # Check some assertions
    try: completeRound(players, 1, 6, 0, 0, 0) # Should fail
    except AssertionError: pass # Should fail
    else: raise ValueError, "Too much balance!"

    completeRound(players, 1, 0, 2, 0, 1)
    players[0].getstatus()

    print 'Triggering'
    contract.trigger(sender=keys[0])
    players[0].update()
    s.mine(15)

    print 'Finalize'
    contract.finalize()
    getstatus()


if __name__ == '__main__':
    try: __IPYTHON__
    except NameError:
        test1()
