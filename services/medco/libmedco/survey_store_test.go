package libmedco_test

import (
	"github.com/dedis/cothority/log"
	"github.com/dedis/cothority/network"
	. "github.com/dedis/cothority/services/medco/libmedco"
	"github.com/dedis/crypto/random"
	"reflect"
	"testing"
)

//TestStoring tests survey store and its methods
func TestStoring(t *testing.T) {
	log.Lvl1("Test beginning")

	//construc variables
	secKey := network.Suite.Scalar().Pick(random.Stream)
	pubKey := network.Suite.Point().Mul(network.Suite.Point().Base(), secKey)
	nullEnc := EncryptInt(pubKey, 0) //*CipherText
	oneEnc := EncryptInt(pubKey, 1)  //*CipherText
	oneBEnc := EncryptInt(pubKey, 1) //*CipherText

	oneEnc.DeterministicSwitching(oneEnc, secKey, pubKey)
	oneBEnc.DeterministicSwitching(oneBEnc, secKey, pubKey)

	var dnull DeterministCipherText
	var done DeterministCipherText
	var doneB DeterministCipherText
	dnull.Point = nullEnc.C
	done.Point = oneEnc.C //deterministic ciphertext
	doneB.Point = oneBEnc.C

	nullVectEnc := NullCipherVector(4, pubKey) //CipherVector
	_ = nullVectEnc
	testCipherVect1 := make(CipherVector, 4)
	for i, p := range []int64{1, 2, 3, 6} {
		testCipherVect1[i] = *EncryptInt(pubKey, p)
	}

	testCipherVect2 := make(CipherVector, 4)
	for i, p := range []int64{2, 4, 8, 6} {
		testCipherVect2[i] = *EncryptInt(pubKey, p)
	}

	//constructor test
	storage := NewSurveyStore()
	_ = storage

	//AddAggregate & GetAggregateLoc Test
	storage.InsertClientResponse(ClientResponse{CipherVector{}, testCipherVect1})

	//veifies that one element has been stored
	if _, aggr := storage.PollLocallyAggregatedResponses(); !(len(aggr) == 1) {
		t.Errorf("aggregation error")
	} else {
		t.Logf("aggregation OK")
	}

	//add a second element with same group ID -> should be aggregated with first one
	storage.InsertClientResponse(ClientResponse{CipherVector{}, testCipherVect2})
	storage.InsertClientResponse(ClientResponse{CipherVector{}, testCipherVect1})

	if _, aggr := storage.PollLocallyAggregatedResponses(); !(len(aggr) == 1) {
		t.Errorf("aggregation error")
	} else {
		added := *testCipherVect1.Add(testCipherVect1, testCipherVect2)
		for i, v := range added {
			if !reflect.DeepEqual(v, aggr[GroupingKey(DefaultGroup)][i]) {
				t.Errorf("aggregation error")
			}
		}
		t.Logf("second aggregation OK")
	}

	//GROUPING
	storage = NewSurveyStore()
	storage.InsertClientResponse(ClientResponse{testCipherVect2, testCipherVect2})
	storage.InsertClientResponse(ClientResponse{testCipherVect1, testCipherVect2})
	storage.InsertClientResponse(ClientResponse{testCipherVect2, testCipherVect1})

	if !(len(storage.ClientResponses) == 3) {
		t.Errorf("insertion error")
	} else {
		t.Logf("insertion OK")
	}

	probaGroups := storage.PollProbabilisticGroupingAttributes()
	//get the indices to use same unique ids for next test steps
	var indexes []TempID
	for i, v := range probaGroups {
		_ = v
		indexes = append(indexes, i)
	}

	groupedAttr := make(map[TempID]GroupingAttributes)
	groupedAttr[indexes[0]] = []DeterministCipherText{dnull, done}
	groupedAttr[indexes[1]] = []DeterministCipherText{dnull, dnull}
	groupedAttr[indexes[2]] = []DeterministCipherText{dnull, doneB} //doneB and done are equal

	storage.PushDeterministicGroupingAttributes(groupedAttr)

	//right size would mean right operations since aggregation has already been verified
	if !(len(storage.LocGroupingAggregating) == 2) {
		t.Errorf("PushDeterministicGroupingAttributes error")
	} else {
		t.Logf("PushDeterministicGroupingAttributestion OK")
	}

	storage.PushCothorityAggregatedGroups(storage.LocGroupingGroups, storage.LocGroupingAggregating)

	//right size would mean right operations since aggregation has already been verified
	if !(len(storage.LocGroupingAggregating) == 2) {
		t.Errorf("PushCothorityAggregatedGroups error")
	} else {
		t.Logf("PushCothorityAggregatedGroups OK")
	}

	groupedDetAttr := storage.PollCothorityAggregatedGroupsID()
	aggrAttr := storage.PollCothorityAggregatedGroupsAttr()
	if !(len(groupedDetAttr) == 2) {
		t.Errorf("PollDeterministicGroupingAttributes error")
	} else {
		t.Logf("PollDeterministicGroupingAttributes OK")
	}

	var indexes1 []TempID
	for i, v := range groupedDetAttr {
		_ = v
		indexes1 = append(indexes1, i)
	}

	reencrGroupAttr := make(map[TempID]CipherVector)
	reencrGroupAttr[indexes1[0]] = testCipherVect2
	reencrGroupAttr[indexes1[1]] = testCipherVect1

	storage.PushQuerierKeyEncryptedData(reencrGroupAttr, aggrAttr)

	if !(len(storage.PollDeliverableResults()) == 2) {
		t.Errorf("PushQuerierKeyEncryptedGroupingAttributes error")
	} else {
		t.Logf("PushQuerierKeyEncryptedGroupingAttributes OK")
	}

	log.Lvl1("... Done")
}
